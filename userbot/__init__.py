from typing import Any, Callable, Coroutine, List, Tuple, Union

from python_socks import parse_proxy_url
from telethon import TelegramClient

from .config import config
from .modules import ALL_MODULES

proxy = None
if config.proxy:
    _parsed = parse_proxy_url(config.proxy.replace("socks5h", "socks5"))
    proxy = {
        "proxy_type": _parsed[0],
        "addr": _parsed[1],
        "port": _parsed[2],
        "username": _parsed[3],
        "password": _parsed[4],
        "rdns": True,
    }
bot = TelegramClient("bot", config.api_id, config.api_hash, proxy=proxy)
bot.parse_mode = "html"
SEARCH_RESULT_TYPE = List[Tuple[str, Union[List[str], List[bytes], str, bytes, None]]]
SEARCH_FUNCTION_TYPE = Callable[..., Coroutine[Any, Any, SEARCH_RESULT_TYPE]]
