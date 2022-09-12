from telethon import TelegramClient
from yarl import URL

from .config import config
from .modules import ALL_MODULES

proxy = (
    ("http", URL(config.proxy).host, URL(config.proxy).port) if config.proxy else None
)
bot = TelegramClient("bot", config.api_id, config.api_hash, proxy=proxy)
bot.parse_mode = "html"
