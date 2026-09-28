import asyncio
import json

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools, register

from .aguess.bank import load_bank
from .aguess.core import Engine, command, reveal, split_message
from .aguess.delivery import send_timeout


@register('astrbot_plugin_a_guess', 'XyeeCheng', '菲比 a一把：十次机会猜算法，逐步揭示中文题意', '1.0.0')
class AGuess(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.engine = None
        self.task = None
        self.lock = asyncio.Lock()
        self.session_locks = {}

    def _session_lock(self, umo):
        return self.session_locks.setdefault(umo, asyncio.Lock())

    async def initialize(self):
        self.engine = Engine(StarTools.get_data_dir() / 'a_guess.sqlite3', load_bank(), self.config)
        self.engine.expire()
        self.task = asyncio.create_task(self._timer(), name='a-guess-expiry')
        logger.info('[a一把] 已加载 %s 道本地题卡', len(self.engine.cards))

    async def terminate(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self.engine:
            self.engine.close()
            self.engine = None

    def _route(self, event):
        pid, sid = event.get_platform_id(), event.get_session_id()
        platform = self.context.get_platform_inst(pid)
        scene = getattr(platform, '_session_scene', {}).get(sid, '') if platform else ''
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
        if self.engine is None:
            await event.send(MessageChain().message('a一把正在初始化，请稍后再试。'))
            return
        action, arg = parsed
        async with self._session_lock(event.unified_msg_origin):
            async with self.lock:
                replies = self.engine.handle(
                    event.unified_msg_origin, event.get_sender_id(),
                    str(getattr(event.message_obj, 'message_id', '') or ''), action, arg,
                    admin=event.is_admin(), route=self._route(event))
            try:
                for reply in replies:
                    for chunk in split_message(reply):
                        await event.send(MessageChain().message(chunk))
            except Exception:
                logger.warning('[a一把] 事件回复失败；进度已保存，可用 a进度 / a题解 重看。')

    async def _timer(self):
        while True:
            await asyncio.sleep(5)
            try:
                async with self.lock:
                    self.engine.expire()
                    if not self.config.get('proactive_timeout', True):
                        continue
                    pending = self.engine.pending()
                for row in pending:
                    async with self._session_lock(row['umo']):
                        if not self.engine.claim_delivery(row['id']):
                            continue
                        state = json.loads(row['state'])
                        outcome = 'acknowledged'
                        for chunk in split_message(reveal(state)):
                            outcome = await send_timeout(self.context, state.get('route', {}), chunk)
                            if outcome != 'acknowledged':
                                break
                        self.engine.delivery_result(row['id'], outcome)
                        if outcome != 'acknowledged':
                            logger.info('[a一把] 超时结算未取得完整回执，下次游戏交互提供结算。')
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('[a一把] 超时检查异常；下一轮继续')
