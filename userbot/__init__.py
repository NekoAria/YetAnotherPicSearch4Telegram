from typing import Any, Callable, Coroutine, List, Tuple, Union

from telethon import TelegramClient
from yarl import URL

from .config import config
from .modules import ALL_MODULES

proxy = (
    ("http", URL(config.proxy).host, URL(config.proxy).port) if config.proxy else None
)
bot = TelegramClient("bot", config.api_id, config.api_hash, proxy=proxy)
bot.parse_mode = "html"
SEARCH_RESULT_TYPE = List[Tuple[str, Union[List[str], List[bytes], str, bytes, None]]]
SEARCH_FUNCTION_TYPE = Callable[..., Coroutine[Any, Any, SEARCH_RESULT_TYPE]]
