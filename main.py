import asyncio
import json
import weakref

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register

from .aguess.bank import load_bank
from .aguess.core import Engine, command, reveal, split_message
from .aguess.delivery import send_timeout
from .aguess.version import PLUGIN_VERSION


@register('astrbot_plugin_a_guess', 'XyeeCheng', '菲比 a一把：十次机会猜算法，逐步揭示中文题意', PLUGIN_VERSION)
class AGuess(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.engine = None
        self.task = None
        self.lock = asyncio.Lock()
        self.session_locks = weakref.WeakValueDictionary()
        self.handlers = set()
        self.stopping = False

    def _session_lock(self, umo):
        return self.session_locks.setdefault(umo, asyncio.Lock())

    async def initialize(self):
        self.stopping = False
        self.engine = Engine(StarTools.get_data_dir() / 'a_guess.sqlite3', load_bank(), self.config)
        self.engine.expire()
        self.task = asyncio.create_task(self._timer(), name='a-guess-expiry')
        logger.info('[a一把] 已加载 %s 道本地题卡', len(self.engine.cards))

    async def terminate(self):
        self.stopping = True
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self.handlers:
            await asyncio.gather(*list(self.handlers), return_exceptions=True)
        if self.engine:
            self.engine.close()
            self.engine = None

    def _route(self, event):
        pid, sid = event.get_platform_id(), event.get_session_id()
        try:
            platform = self.context.get_platform_inst(pid)
            scene = getattr(platform, '_session_scene', {}).get(sid, '') if platform else ''
        except Exception:
            scene = ''
        return {'platform_id': pid, 'platform_name': event.get_platform_name(),
                'session_id': sid, 'scene': scene}

    @filter.event_message_type(filter.EventMessageType.ALL, priority=90)
    async def on_message(self, event: AstrMessageEvent):
        parsed = command(event.message_str, self.config.get('wake_prefixes', ['菲比', '啾比']))
        if not parsed:
            return
        if self.config.get('require_wake', True) and not event.is_private_chat() and not event.is_at_or_wake_command:
            return
        event.stop_event()
        if self.engine is None or self.stopping:
            await event.send(MessageChain().message('a一把正在初始化，请稍后再试。'))
            return
        task = asyncio.create_task(self._handle_message(event, *parsed))
        self.handlers.add(task)
        try:
            await task
        finally:
            self.handlers.discard(task)

    async def _handle_message(self, event, action, arg):
        async with self._session_lock(event.unified_msg_origin):
            async with self.lock:
                replies = self.engine.handle(
                    event.unified_msg_origin, event.get_sender_id(),
                    str(getattr(event.message_obj, 'message_id', '') or ''), action, arg,
                    admin=event.is_admin(), route=self._route(event))
            try:
                for reply in replies:
                    outcome = 'unknown'
                    try:
                        for chunk in split_message(reply):
                            await asyncio.wait_for(event.send(MessageChain().message(chunk)), timeout=20)
                        outcome = 'event_reply'
                    finally:
                        self.engine.reply_result(reply, outcome)
            except Exception:
                logger.warning('[a一把] 事件回复失败；进度已保存，可用 a进度 / a上局 重看。')

    async def _send_pending(self, row):
        async with self._session_lock(row['umo']):
            if not self.engine.claim_delivery(row['id']):
                return
            outcome = 'unknown'
            try:
                state = json.loads(row['state'])
                outcome = 'acknowledged'
                for chunk in split_message(reveal(state)):
                    outcome = await send_timeout(self.context, state.get('route', {}), chunk)
                    if outcome != 'acknowledged':
                        break
            except asyncio.CancelledError:
                outcome = 'unknown'
                raise
            except Exception:
                outcome = 'unknown'
                logger.warning('[a一把] 单条结算投递异常，已保存为未确认。')
            finally:
                self.engine.delivery_result(row['id'], outcome)

    async def _drain_pending(self, rows):
        queue = iter(rows)

        async def worker():
            for row in queue:
                await self._send_pending(row)

        await asyncio.gather(*(worker() for _ in range(min(len(rows), self.engine.config['timeout_concurrency']))))

    async def _timer(self):
        while True:
            await asyncio.sleep(5)
            try:
                async with self.lock:
                    self.engine.expire()
                    if not self.config.get('proactive_timeout', True):
                        continue
                    pending = self.engine.pending()
                await self._drain_pending(pending)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('[a一把] 超时检查异常；下一轮继续')
