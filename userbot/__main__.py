import sys
from importlib import import_module

from loguru import logger

from userbot import ALL_MODULES, bot

from .config import config

bot.start(bot_token=config.token)
logger.info("Bot started!")

if not config.saucenao_api_key:
    logger.warning("Missing `saucenao_api_key` !")
    sys.exit(1)
for module in ALL_MODULES:
    import_module(f"userbot.modules.{module}")
    logger.info(f"Module: [{module}] loaded!")
logger.info("Bot inited!")
bot.run_until_disconnected()
