"""Conservative QQ Official timer delivery with a real platform receipt."""
import asyncio


def receipt_id(value):
    if isinstance(value, dict):
        nested = value.get('data')
        candidate = value.get('id') or (nested.get('id') if isinstance(nested, dict) else None)
    else:
        candidate = getattr(value, 'id', None)
    return candidate if isinstance(candidate, str) and candidate.strip() else None


async def send_timeout(context, route, text):
    # A route must originate from a real event; never turn a guild/private chat into a group.
    if route.get('platform_name') != 'qq_official' or route.get('scene') != 'group':
        return 'blocked'
    try:
        platform = context.get_platform_inst(route.get('platform_id', ''))
        meta = platform.meta() if platform is not None else None
        if platform is None or getattr(meta, 'name', None) != 'qq_official' or getattr(meta, 'id', None) != route.get('platform_id'):
            return 'blocked'
        api = getattr(getattr(platform, 'client', None), 'api', None)
        if not api or not callable(getattr(api, 'post_group_message', None)) or not route.get('session_id'):
            return 'blocked'
    except Exception:
        # Adapter lookup failed before any network request was attempted.
        return 'blocked'
    # No cached/forged msg_id. QQ permissions are enforced by QQ's own API.
    try:
        result = await asyncio.wait_for(api.post_group_message(
            group_openid=route['session_id'], msg_type=0, content=text), timeout=20)
    except asyncio.CancelledError:
        raise
    except Exception:
        # An exception could follow a successful send, so do not auto-retry.
        return 'unknown'
    return 'acknowledged' if receipt_id(result) else 'unknown'
