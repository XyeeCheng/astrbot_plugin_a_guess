import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from aguess.delivery import send_timeout


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api=SimpleNamespace(post_group_message=AsyncMock(return_value={'id':'server-receipt'}))
        self.platform=SimpleNamespace(meta=lambda:SimpleNamespace(name='qq_official',id='phoebe'),client=SimpleNamespace(api=self.api))
        self.context=SimpleNamespace(get_platform_inst=lambda _:self.platform)
        self.route={'platform_name':'qq_official','platform_id':'phoebe','scene':'group','session_id':'OpenId_Abc'}

    async def test_real_receipt_required(self):
        self.assertEqual(await send_timeout(self.context,self.route,'text'),'acknowledged')
        self.api.post_group_message.assert_awaited_once_with(group_openid='OpenId_Abc',msg_type=0,content='text')

    async def test_true_is_not_receipt(self):
        for response in (True, {'id': True}, {'id': ' '}, {'data': True}, {'data': []}, None):
            with self.subTest(response=response):
                self.api.post_group_message.return_value=response
                self.assertEqual(await send_timeout(self.context,self.route,'text'),'unknown')

    async def test_nested_receipt(self):
        self.api.post_group_message.return_value={'data': {'id': 'nested-receipt'}}
        self.assertEqual(await send_timeout(self.context,self.route,'text'),'acknowledged')

    async def test_adapter_lookup_failure_is_blocked(self):
        def failing_meta():
            raise RuntimeError('adapter unloading')
        self.platform.meta=failing_meta
        self.assertEqual(await send_timeout(self.context,self.route,'text'),'blocked')
        self.api.post_group_message.assert_not_awaited()

    async def test_no_private_or_guild_to_group(self):
        for scene in ('friend','channel',''):
            self.assertEqual(await send_timeout(self.context,{**self.route,'scene':scene},'text'),'blocked')
        self.api.post_group_message.assert_not_awaited()

    async def test_instance_mismatch(self):
        self.platform.meta=lambda:SimpleNamespace(name='qq_official',id='nailong')
        self.assertEqual(await send_timeout(self.context,self.route,'text'),'blocked')
        self.api.post_group_message.assert_not_awaited()

    async def test_exception_uncertain_no_retry(self):
        self.api.post_group_message.side_effect=TimeoutError()
        self.assertEqual(await send_timeout(self.context,self.route,'text'),'unknown')
        self.assertEqual(self.api.post_group_message.await_count,1)

    async def test_adapter_not_ready(self):
        self.context.get_platform_inst=lambda _:None
        self.assertEqual(await send_timeout(self.context,self.route,'text'),'blocked')


if __name__ == '__main__': unittest.main()
