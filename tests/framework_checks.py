"""Run explicitly in an installed AstrBot environment; uses no real IM transport."""
import asyncio
import gc
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from smoke_astrbot import CapturedEvent, StarTools, module


class AdapterChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_patch = patch.object(StarTools, 'get_data_dir', return_value=Path(self.tmp.name))
        self.data_patch.start()
        context = SimpleNamespace(get_platform_inst=lambda _: SimpleNamespace(_session_scene={'OpenId_Abc': 'group'}))
        self.plugin = module.AGuess(context, {'proactive_timeout': False, 'timeout_concurrency': 2})
        await self.plugin.initialize()
        self.plugin.task.cancel()
        try:
            await self.plugin.task
        except asyncio.CancelledError:
            pass
        self.plugin.task = None

    async def asyncTearDown(self):
        await self.plugin.terminate()
        self.data_patch.stop()
        self.tmp.cleanup()

    def status(self, game_id):
        return self.plugin.engine.db.execute('SELECT delivery FROM history WHERE id=?', (game_id,)).fetchone()[0]

    def pending(self, umo='fixture:GroupMessage:group-a'):
        engine = self.plugin.engine
        engine.handle(umo, 'owner', 'start-' + umo, '一把', route={'session_id': umo})
        state = engine.active(umo)
        with engine.transaction():
            engine.finish(umo, state, 'timeout')
        return next(r for r in engine.pending() if r['umo'] == umo)

    async def test_event_send_failure_remains_recoverable_in_new_round(self):
        start = CapturedEvent('a一把', '1')
        await self.plugin.on_message(start)
        class FailedEvent(CapturedEvent):
            async def send(self, chain):
                raise OSError('injected transport failure')
        await self.plugin.on_message(FailedEvent('a结束', '2'))
        previous = self.plugin.engine.last(start.unified_msg_origin)
        self.assertEqual(self.status(previous['id']), 'unknown')
        next_round = CapturedEvent('a再来', '3')
        await self.plugin.on_message(next_round)
        self.assertIn('此前投递未确认', '\n'.join(next_round.sent))
        self.assertEqual(self.status(previous['id']), 'event_reply')
        active = self.plugin.engine.active(start.unified_msg_origin)
        last = CapturedEvent('a上局', '4')
        await self.plugin.on_message(last)
        self.assertIn(previous['card']['source'], '\n'.join(last.sent))
        self.assertEqual(active, self.plugin.engine.active(start.unified_msg_origin))

    async def test_partial_chunk_send_is_uncertain(self):
        await self.plugin.on_message(CapturedEvent('a一把', '1'))
        class PartialEvent(CapturedEvent):
            async def send(self, chain):
                if self.sent:
                    raise TimeoutError('second chunk uncertain')
                await super().send(chain)
        stop = PartialEvent('a结束', '2')
        with patch.object(module, 'split_message', return_value=['first chunk', 'second chunk']):
            await self.plugin.on_message(stop)
        previous = self.plugin.engine.last(stop.unified_msg_origin)
        self.assertEqual(self.status(previous['id']), 'unknown')
        self.assertEqual(stop.sent, ['first chunk'])

    async def test_cancelled_event_resolves_pending_status(self):
        await self.plugin.on_message(CapturedEvent('a一把', '1'))
        entered = asyncio.Event()
        class WaitingEvent(CapturedEvent):
            async def send(self, chain):
                entered.set()
                await asyncio.Event().wait()
        stop = WaitingEvent('a结束', '2')
        task = asyncio.create_task(self.plugin.on_message(stop))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        previous = self.plugin.engine.last(stop.unified_msg_origin)
        self.assertEqual(self.status(previous['id']), 'unknown')
        self.assertFalse(self.plugin.handlers)

    async def test_unexpected_timeout_error_never_stays_sending(self):
        row = self.pending()
        with patch.object(module, 'reveal', side_effect=ValueError('injected invalid record')):
            await self.plugin._send_pending(row)
        self.assertEqual(self.status(row['id']), 'unknown')
        self.assertFalse(self.plugin.engine.pending())

    async def test_timeout_cancellation_is_not_retried(self):
        row = self.pending()
        entered = asyncio.Event()
        async def wait_send(*args):
            entered.set()
            await asyncio.Event().wait()
        with patch.object(module, 'send_timeout', side_effect=wait_send):
            task = asyncio.create_task(self.plugin._send_pending(row))
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(self.status(row['id']), 'unknown')
        self.assertFalse(self.plugin.engine.pending())

    async def test_groups_deliver_concurrently_with_bounded_workers_and_one_claim(self):
        rows = [self.pending(f'fixture:GroupMessage:{i}') for i in range(5)]
        release, two_started, later_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls, running, peak = [], 0, 0
        async def send(context, route, text):
            nonlocal running, peak
            calls.append(route['session_id'])
            running += 1
            peak = max(peak, running)
            if len(calls) == 2:
                two_started.set()
            if len(calls) >= 3:
                later_started.set()
            if route['session_id'].endswith(':0'):
                await release.wait()
            else:
                await asyncio.sleep(0)
            running -= 1
            return 'acknowledged'
        with patch.object(module, 'send_timeout', side_effect=send), patch.object(module, 'split_message', return_value=['one chunk']):
            task = asyncio.create_task(self.plugin._drain_pending(rows))
            await asyncio.wait_for(two_started.wait(), 2)
            await asyncio.wait_for(later_started.wait(), 2)
            self.assertFalse(task.done())  # Slow first group does not block later groups.
            release.set()
            await asyncio.wait_for(task, 2)
            await self.plugin._drain_pending(rows)
        self.assertEqual(len(calls), 5)
        self.assertLessEqual(peak, 2)
        for row in rows:
            self.assertEqual(self.status(row['id']), 'acknowledged')

    async def test_shutdown_waits_for_inflight_replies_before_closing_sqlite(self):
        await self.plugin.on_message(CapturedEvent('a一把', '1'))
        entered, release = asyncio.Event(), asyncio.Event()
        class WaitingEvent(CapturedEvent):
            async def send(self, chain):
                entered.set()
                await release.wait()
                await super().send(chain)
        task = asyncio.create_task(self.plugin.on_message(WaitingEvent('a结束', '2')))
        await asyncio.wait_for(entered.wait(), 2)
        stopping = asyncio.create_task(self.plugin.terminate())
        await asyncio.sleep(0)
        self.assertIsNotNone(self.plugin.engine)
        release.set()
        await asyncio.wait_for(asyncio.gather(task, stopping), 2)
        self.assertIsNone(self.plugin.engine)

    async def test_same_group_message_waits_for_timer_delivery(self):
        event = CapturedEvent('a一把', 'next-round')
        row = self.pending(event.unified_msg_origin)
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed_send(*args):
            entered.set()
            await release.wait()
            return 'acknowledged'
        with patch.object(module, 'send_timeout', side_effect=delayed_send):
            timer = asyncio.create_task(self.plugin._send_pending(row))
            await asyncio.wait_for(entered.wait(), 2)
            message = asyncio.create_task(self.plugin.on_message(event))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertIsNone(self.plugin.engine.active(event.unified_msg_origin))
            release.set()
            await asyncio.wait_for(asyncio.gather(timer, message), 2)
        self.assertIsNotNone(self.plugin.engine.active(event.unified_msg_origin))
        self.assertEqual(self.status(row['id']), 'acknowledged')
        self.assertNotIn('此前投递未确认', '\n'.join(event.sent))

    async def test_unused_session_locks_are_reclaimed(self):
        for i in range(100):
            async with self.plugin._session_lock(str(i)):
                pass
        gc.collect()
        self.assertEqual(len(self.plugin.session_locks), 0)


if __name__ == '__main__':
    unittest.main()
