from typing import List, Optional, Tuple, Union

from aiohttp import ClientSession
from loguru import logger
from PicImageSearch import Network
from telethon import TelegramClient, events
from telethon.events import CallbackQuery
from telethon.tl.custom import Button
from telethon.tl.patched import Message
from tenacity import AsyncRetrying, stop_after_attempt, stop_after_delay
from yarl import URL

from .ascii2d import ascii2d_search
from .config import config
from .ehentai import ehentai_search
from .iqdb import iqdb_search
from .saucenao import saucenao_search
from .utils import get_image_bytes_by_url
from .whatanime import whatanime_search

proxy = (
    ("http", URL(config.proxy).host, URL(config.proxy).port) if config.proxy else None
)
bot = TelegramClient("bot", config.api_id, config.api_hash, proxy=proxy).start(
    bot_token=config.token
)
bot_name = ""
allowed_users = [config.owner_id] + config.allowed_users
search_buttons = [
    [
        Button.inline("Ascii2D"),
        Button.inline("Iqdb"),
        Button.inline("SauceNAO"),
    ],
    [
        Button.inline("Pixiv"),
        Button.inline("Danbooru"),
    ],
    [
        Button.inline("WhatAnime"),
        Button.inline("Anime"),
    ],
    [
        Button.inline("EHentai"),
        Button.inline("Doujin"),
    ],
]


def check_permission(
    event: Union[events.NewMessage.Event, events.Album.Event, CallbackQuery.Event]
) -> bool:
    return event.sender_id in allowed_users or event.chat_id in config.allowed_chats


@bot.on(events.NewMessage(from_users=allowed_users, pattern="/start"))  # type: ignore
async def start(event: events.NewMessage.Event) -> None:
    await event.reply("请发送图片，然后选择搜图模式")


async def is_mentioned_or_is_command(
    event: Union[events.NewMessage.Event, events.Album.Event]
) -> bool:
    global bot_name
    if not bot_name:
        bot_name = (await bot.get_me()).username
    if f"@{bot_name}" in event.text or "搜图" in event.text:
        return True
    return False


@bot.on(events.NewMessage(func=check_permission))  # type: ignore
@bot.on(events.Album(func=check_permission))  # type: ignore
async def handle_photo_messages(
    event: Union[events.NewMessage.Event, events.Album.Event]
) -> None:
    if (event.is_group or event.is_channel) and not await is_mentioned_or_is_command(
        event
    ):
        return
    if isinstance(event, events.NewMessage.Event) and not event.photo:
        if event.is_reply:
            reply_to_msg = await event.get_reply_message()
            await bot.send_message(
                reply_to_msg.peer_id,
                "请选择搜图模式",
                buttons=search_buttons,
                reply_to=reply_to_msg,
            )
    elif (
        isinstance(event, events.NewMessage.Event)
        and event.photo
        and not event.grouped_id
    ) or (isinstance(event, events.Album.Event)):
        await event.reply("请选择搜图模式", buttons=search_buttons)


@bot.on(CallbackQuery(func=check_permission))  # type: ignore
async def get_search_results(event: events.CallbackQuery) -> None:
    reply_to_msg = await event.get_message()
    peer_id = reply_to_msg.peer_id
    msgs = await get_messages_to_search(reply_to_msg)
    if not event.is_private:
        await bot.delete_messages(peer_id, message_ids=reply_to_msg.id)
    network = (
        Network(proxies=config.proxy, cookies=config.exhentai_cookies, timeout=60)
        if event.data == b"EHentai"
        else Network(proxies=config.proxy)
    )
    async with network as client:
        for msg in msgs:
            tips_msg = await bot.send_message(peer_id, "正在进行搜索，请稍候", reply_to=msg)
            try:
                async for attempt in AsyncRetrying(
                    stop=(stop_after_attempt(3) | stop_after_delay(30)), reraise=True
                ):
                    with attempt:
                        file = await bot.download_media(msg.photo, file=bytes)
                        results = await handle_search(event.data, file, client)
                        for caption, file in results:
                            await send_search_results(
                                bot, peer_id, caption, msg, file=file
                            )
            except Exception as e:
                logger.exception(e)
                await bot.send_message(peer_id, f"该图搜图失败\nE: {repr(e)}", reply_to=msg)
            await bot.delete_messages(peer_id, message_ids=tips_msg.id)


async def get_messages_to_search(msg: Message) -> List[Message]:
    msgs: List[Message] = await bot.get_messages(
        msg.peer_id, ids=[msg.reply_to.reply_to_msg_id]
    )
    if grouped_id := msgs[0].grouped_id:
        first_msg_id = msgs[0].id
        msgs = []
        for i in await bot.get_messages(
            msg.peer_id, ids=list(range(first_msg_id, first_msg_id + 100))
        ):
            if not i or not i.photo:
                break
            elif hasattr(i, "grouped_id") and i.grouped_id == grouped_id:
                msgs.append(i)
    return msgs


async def handle_search(
    event_data: bytes, file: bytes, client: ClientSession
) -> List[Tuple[str, Optional[bytes]]]:
    if event_data == b"Ascii2D":
        return await ascii2d_search(file=file, client=client)
    elif event_data == b"Iqdb":
        return await iqdb_search(file=file, client=client)
    elif event_data == b"WhatAnime":
        return await whatanime_search(file=file, client=client)
    elif event_data == b"EHentai":
        return await ehentai_search(file=file, client=client)
    elif event_data == b"SauceNAO":
        return await saucenao_search(file=file, mode="all", client=client)
    elif event_data == b"Pixiv":
        return await saucenao_search(file=file, mode="pixiv", client=client)
    elif event_data == b"Danbooru":
        return await saucenao_search(file=file, mode="danbooru", client=client)
    elif event_data == b"Anime":
        return await saucenao_search(file=file, mode="anime", client=client)
    elif event_data == b"Doujin":
        return await saucenao_search(file=file, mode="doujin", client=client)
    return []


async def send_search_results(
    _bot: TelegramClient,
    send_to: int,
    caption: str,
    reply_to: Message,
    file: Optional[bytes] = None,
) -> None:
    if file:
        await _bot.send_file(send_to, file=file, caption=caption, reply_to=reply_to)
    else:
        await _bot.send_message(send_to, caption, reply_to=reply_to)


def main() -> None:
    if not config.saucenao_api_key:
        logger.warning("请配置 saucenao_api_key")
        return
    logger.info("Bot started")
    bot.run_until_disconnected()
