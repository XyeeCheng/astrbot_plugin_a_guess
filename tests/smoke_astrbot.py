"""Run inside an installed AstrBot environment, without starting a bot or network."""
import asyncio
import importlib.util
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import StarTools
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.message.components import Plain

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('a_guess_smoke', ROOT / 'main.py', submodule_search_locations=[str(ROOT)])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class CapturedEvent(AstrMessageEvent):
    def __init__(self, text, eid, wake=True):
        msg = AstrBotMessage()
        msg.type = MessageType.GROUP_MESSAGE
        msg.self_id = 'fake-bot'
        msg.sender = MessageMember(user_id='owner', nickname='tester')
        msg.message = [Plain(text)]
        msg.message_str = text
        msg.message_id = eid
        msg.group_id = 'OpenId_Abc'
        super().__init__(text, msg, PlatformMetadata(name='qq_official', description='test', id='phoebe'), 'OpenId_Abc')
        self.is_at_or_wake_command = wake
        self.sent = []

    async def send(self, chain):
        self.sent.append(''.join(getattr(x, 'text', '') for x in chain.chain))


async def run():
    platform = SimpleNamespace(_session_scene={'OpenId_Abc': 'group'})
    context = SimpleNamespace(get_platform_inst=lambda _: platform)
    with tempfile.TemporaryDirectory() as directory, patch.object(StarTools, 'get_data_dir', return_value=Path(directory)):
        plugin = module.AGuess(context, {'proactive_timeout': False, 'hint_cooldown': 0})
        await plugin.initialize()
        task = plugin.task
        ignored = CapturedEvent('提示', '0')
        await plugin.on_message(ignored)
        assert not ignored.sent
        asleep = CapturedEvent('a一把', '1', wake=False)
        await plugin.on_message(asleep)
        assert not asleep.sent
        start = CapturedEvent('a一把 困难', '2')
        await plugin.on_message(start)
        assert '没有题目提示' in start.sent[0]
        hint = CapturedEvent('a提示', '3')
        await plugin.on_message(hint)
        assert '线索 1/9' in hint.sent[0]
        stop = CapturedEvent('a结束', '4')
        await plugin.on_message(stop)
        assert 'https://codeforces.com/' in '\n'.join(stop.sent)
        assert '中文题意' in '\n'.join(stop.sent)
        await plugin.terminate()
        assert task.cancelled() and plugin.engine is None
        await plugin.initialize()
        assert plugin.engine.last(start.unified_msg_origin)
        await plugin.terminate()
    print('AstrBot integration smoke: import, initialize, wake, commands, replies, terminate, reload PASS')


if __name__ == '__main__':
    asyncio.run(run())
