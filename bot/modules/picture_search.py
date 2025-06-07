from asyncio import TimeoutError
from io import BytesIO
from itertools import takewhile
from typing import Optional, Union

from cachetools import TTLCache
from cachetools.keys import hashkey
from httpx import AsyncClient
from loguru import logger
from PicImageSearch import Network
from PIL import Image
from telethon import TelegramClient, events
from telethon.errors import (
    ImageProcessFailedError,
    MediaCaptionTooLongError,
    MessageNotModifiedError,
)
from telethon.events import CallbackQuery
from telethon.hints import EntityLike
from telethon.tl.custom import Button
from telethon.tl.patched import Message
from tenacity import TryAgain, retry, stop_after_attempt, stop_after_delay

from .. import SEARCH_FUNCTION_TYPE, SEARCH_RESULT_TYPE, bot
from ..ascii2d import ascii2d_search
from ..baidu import baidu_search
from ..config import config
from ..ehentai import ehentai_search
from ..google import google_search
from ..iqdb import iqdb_search
from ..saucenao import saucenao_search
from ..utils import async_cached, command, get_first_frame_from_video, remove_button
from ..whatanime import whatanime_search
from ..yandex import yandex_search

bot_name = ""
allowed_users = [config.owner_id] + config.allowed_users
search_mode_tips = "请选择搜图模式"
search_buttons = [
    [
        Button.inline("Ascii2D"),
        Button.inline("Iqdb"),
        Button.inline("SauceNAO"),
    ],
    [
        Button.inline("Baidu"),
        Button.inline("Google"),
        Button.inline("Yandex"),
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
search_button_texts = [
    "Ascii2D",
    "Iqdb",
    "SauceNAO",
    "Baidu",
    "Google",
    "Yandex",
    "Pixiv",
    "Danbooru",
    "WhatAnime",
    "Anime",
    "EHentai",
    "Doujin",
]


def check_permission(event: Union[events.NewMessage.Event, events.Album.Event, CallbackQuery.Event]) -> bool:
    return event.sender_id in allowed_users or event.chat_id in config.allowed_chats


@command(pattern="/start", from_users=allowed_users)
async def start(event: events.NewMessage.Event) -> None:
    await event.reply("请发送图片，然后选择搜图模式")


async def is_mentioned_or_get_command(event: Union[events.NewMessage.Event, events.Album.Event]) -> bool:
    global bot_name
    if not bot_name:
        bot_name = (await bot.get_me()).username
    return f"@{bot_name}" in event.text or "搜图" in event.text


def is_photo_or_video(event_or_message: Union[events.NewMessage.Event, Message]) -> bool:
    if event_or_message.photo:
        return True
    elif document := event_or_message.document:
        if document.mime_type.startswith("image/") or document.mime_type == "video/mp4":
            return True
    return False


async def wait_callback(event: Union[events.NewMessage.Event, events.Album.Event], reply_to_msg: Message) -> None:
    if event.is_private:
        await bot.send_message(
            event.chat_id,
            search_mode_tips,
            buttons=search_buttons,
            reply_to=reply_to_msg,
        )
    else:
        async with bot.conversation(event.chat_id, timeout=180, exclusive=False) as conv:
            msg = await conv.send_message(
                search_mode_tips,
                buttons=search_buttons,
                reply_to=reply_to_msg,
            )
            while True:
                try:
                    resp = await conv.wait_event(events.CallbackQuery(func=lambda e: e.sender_id == event.sender_id))
                    await handle_search(resp)
                except TimeoutError:
                    break
        await msg.delete()


@bot.on(events.NewMessage(func=check_permission))  # type: ignore
@bot.on(events.Album(func=check_permission))  # type: ignore
async def handle_message_event(event: Union[events.NewMessage.Event, events.Album.Event]) -> None:
    if (event.is_group or event.is_channel) and not await is_mentioned_or_get_command(event):
        return
    if (
        isinstance(event, events.NewMessage.Event)
        and not event.grouped_id
        and (is_photo_or_video(event) or event.is_reply)
    ):
        reply_to_msg = await event.get_reply_message() if event.is_reply else event.message
        await wait_callback(event, reply_to_msg)
    elif isinstance(event, events.Album.Event):
        await wait_callback(event, event.messages[0])


def filter_private_and_search(event: events.CallbackQuery.Event) -> bool:
    return event.data.decode() in search_button_texts if event.is_private else False


@bot.on(CallbackQuery(func=filter_private_and_search))  # type: ignore
async def handle_search(event: events.CallbackQuery.Event) -> None:
    search_engine_or_type = event.data.decode()
    reply_to_msg: Message = await event.get_message()
    buttons = remove_button(reply_to_msg.buttons, event.data)
    # 奇怪的 BUG：有时候会间隔 N 秒连续触发同一个按钮的点击事件
    try:
        await reply_to_msg.edit(text=f"正在进行 {search_engine_or_type} 搜索，请稍候。", buttons=None)
    except MessageNotModifiedError:
        return
    if is_photo_or_video(reply_to_msg):
        msgs = [reply_to_msg]
    else:
        msgs = await get_messages_to_search(reply_to_msg)
        if not msgs:
            await bot.send_message(event.chat_id, "没有获取到图片或视频", reply_to=reply_to_msg)
            return

    if search_engine_or_type == "EHentai":
        cookies = config.exhentai_cookies
    elif search_engine_or_type == "Google":
        cookies = config.google_cookies
    else:
        cookies = None

    network = Network(proxies=config.proxy, cookies=cookies)

    async with network as client:
        for msg in msgs:
            try:
                _file = await get_file_from_message(msg, event.chat_id)
                if not _file:
                    continue
                result = await handle_search_mode(event.data, _file, client)
                for caption, __file in result:
                    if "暂时无法使用" in caption:
                        await bot.send_message(
                            event.chat_id,
                            caption,
                            reply_to=msg,
                            buttons=[Button.inline(search_engine_or_type)],
                        )
                    else:
                        await send_search_results(bot, event.chat_id, caption, msg, file=__file)
            except Exception as e:
                logger.exception(e)
                await bot.send_message(
                    event.chat_id,
                    f"该图搜图失败\n\nE: {repr(e)}\n\n请稍后重试：",
                    reply_to=msg,
                    buttons=[Button.inline(search_engine_or_type)],
                )
    await reply_to_msg.edit(text=search_mode_tips, buttons=buttons)


@async_cached(cache=TTLCache(maxsize=16, ttl=180), key=lambda msg, chat_id: hashkey(msg.id, chat_id))  # type: ignore
async def get_file_from_message(msg: Message, chat_id: EntityLike) -> Optional[bytes]:
    if (document := msg.document) and document.mime_type == "video/mp4":
        if document.size > 10 * 1024 * 1024:
            await bot.send_message(chat_id, "跳过超过 10M 的视频", reply_to=msg)
            return None
        _file = get_first_frame_from_video(await bot.download_media(document, file=bytes))
    elif msg.photo:
        _file = await bot.download_media(msg.photo, file=bytes)
    else:
        _file = await bot.download_media(msg.document, file=bytes)
    if not _file:
        await bot.send_message(chat_id, "图片或视频获取失败", reply_to=msg)
        return None
    return _file


async def get_messages_to_search(msg: Message) -> list[Message]:
    msgs = await bot.get_messages(msg.peer_id, ids=[msg.reply_to.reply_to_msg_id])
    if grouped_id := msgs[0].grouped_id:
        last_100_messages = await bot.get_messages(msg.peer_id, ids=list(range(msgs[0].id, msgs[0].id + 100)))
        msgs = list(
            takewhile(
                lambda x: x and x.grouped_id == grouped_id,
                last_100_messages,
            )
        )
    return [i for i in msgs if is_photo_or_video(i)]


@retry(stop=(stop_after_attempt(3)), reraise=True)
@async_cached(cache=TTLCache(maxsize=16, ttl=180))  # type: ignore
async def handle_search_mode(event_data: bytes, file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    search_function_dict: dict[bytes, SEARCH_FUNCTION_TYPE] = {
        "Ascii2D": ascii2d_search,
        "Baidu": baidu_search,
        "EHentai": ehentai_search,
        "Google": google_search,
        "Iqdb": iqdb_search,
        "WhatAnime": whatanime_search,
        "Yandex": yandex_search,
        "SauceNAO": lambda file, client: saucenao_search(file, client, "all"),
    }
    search_function = search_function_dict.get(
        event_data.decode(),
        lambda file, client: saucenao_search(file, client, event_data.decode().lower()),
    )
    return await search_function(file, client)


@retry(stop=(stop_after_attempt(3) | stop_after_delay(30)), reraise=True)
async def send_search_results(
    _bot: TelegramClient,
    send_to: int,
    caption: str,
    reply_to: Message,
    file: Union[list[str], list[bytes], str, bytes, None] = None,
) -> None:
    if send_to != config.owner_id and "已收藏" in caption:
        caption = caption.replace("❤️ 已收藏\n", "")

    if file:
        prepared_files = []
        if not isinstance(file, list):
            file = [file]

        file = [f for f in file if f]
        if not file:
            await _bot.send_message(send_to, caption, reply_to=reply_to, link_preview=False)
            return

        for f in file:
            if isinstance(f, bytes):
                with Image.open(BytesIO(f)) as im:
                    file_stream = BytesIO(f)
                    file_stream.name = f"image.{im.format.lower()}"
                    prepared_files.append(file_stream)
            else:
                prepared_files.append(f)
        try:
            await _bot.send_file(send_to, file=prepared_files, caption=caption, reply_to=reply_to, link_preview=False)
        except MediaCaptionTooLongError:
            await _bot.send_message(send_to, caption, reply_to=reply_to, link_preview=False)
            await _bot.send_file(send_to, file=prepared_files, reply_to=reply_to)
        except ImageProcessFailedError as e:
            raise TryAgain from e
    else:
        await _bot.send_message(send_to, caption, reply_to=reply_to, link_preview=False)
