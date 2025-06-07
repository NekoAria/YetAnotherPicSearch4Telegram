import asyncio
import re
from collections import defaultdict
from collections.abc import Coroutine
from contextlib import suppress
from difflib import SequenceMatcher
from functools import update_wrapper, wraps
from io import BytesIO
from typing import (
    Any,
    Callable,
    Optional,
    TypeVar,
    Union,
)

import arrow
import imageio.v3 as iio
from cachetools.keys import hashkey
from httpx import (
    URL,
    AsyncClient,
    ConnectError,
    ConnectTimeout,
    ReadTimeout,
    UnsupportedProtocol,
)
from loguru import logger
from PicImageSearch.model import EHentaiItem, EHentaiResponse
from PIL import Image, UnidentifiedImageError
from pyquery import PyQuery
from telethon import events
from telethon.tl.custom import MessageButton
from tenacity import TryAgain, retry, stop_after_attempt, stop_after_delay

from . import bot
from .config import config
from .nhentai_model import NHentaiItem, NHentaiResponse

T = TypeVar("T")
SEPARATOR = "\n" + "-" * 22 + "\n"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/99.0.4844.82 Safari/537.36"
    )
}


@retry(stop=(stop_after_attempt(3) | stop_after_delay(30)), reraise=True)
async def get_bytes_by_url(url: str, cookies: Optional[str] = None) -> Optional[bytes]:
    _url = URL(url)
    referer = f"{_url.scheme}://{_url.host}/"
    headers = (
        {"Referer": referer, **DEFAULT_HEADERS}
        if _url.host != "cdn.donmai.us"
        else {"User-Agent": "python-httpx/0.28.2"}
    )
    async with AsyncClient(
        headers=headers,
        cookies=parse_cookies(cookies),
        proxy=config.proxy,
        follow_redirects=True,
    ) as session:
        try:
            resp = await session.get(url)
        except (ConnectError, UnsupportedProtocol):
            return None
        except (ConnectTimeout, ReadTimeout):
            logger.warning(f"Timeout occurred for URL: {url}")
            return None
        except Exception as e:
            logger.error(f"HTTP error occurred: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.info(f"URL: {url}")
            return None

        if resp.status_code in {429, 500, 503}:
            raise TryAgain

        if resp.status_code >= 400:
            if resp.status_code != 404:
                logger.warning(f"Failed request with status code {resp.status_code} for URL: {url}")
            return None

        if len(resp.content) == 0:
            logger.warning(f"No content returned for URL: {url}")
            return None

        try:
            im = Image.open(BytesIO(resp.content))
        except UnidentifiedImageError:
            return resp.content

        if im.format in {"BMP", "WEBP"}:
            with BytesIO() as output:
                im.save(output, "PNG")
                return output.getvalue()

        return resp.content


def handle_source(source: str) -> str:
    return (
        source.replace("www.pixiv.net/en/artworks", "www.pixiv.net/artworks")
        .replace(
            "www.pixiv.net/member_illust.php?mode=medium&illust_id=",
            "www.pixiv.net/artworks/",
        )
        .replace("http://", "https://")
    )


def parse_source(resp_text: str, host: str) -> str:
    doc = PyQuery(resp_text)
    source: Optional[str] = None

    if host in {"danbooru.donmai.us", "gelbooru.com"}:
        source = doc(".image-container").attr("data-normalized-source")

    elif host in {"yande.re", "konachan.com"}:
        source = doc("#post_source").attr("value") or doc('a[href^="/pool/show/"]').text()

    return source or ""


async def get_source(url: str) -> str:
    if not url:
        return ""

    _url = get_valid_url(url)
    if not _url:
        return ""

    host = _url.host
    headers = {"User-Agent": "python-httpx/0.28.2"} if host == "danbooru.donmai.us" else DEFAULT_HEADERS
    async with AsyncClient(headers=headers, proxy=config.proxy, follow_redirects=True) as session:
        resp = await session.get(url)
        if resp.status_code >= 400:
            return ""

        source = parse_source(resp.text, host)
        if source and get_valid_url(source):
            return handle_source(source)

    return source or ""


def get_website_mark(href: str) -> str:
    if url := get_valid_url(href):
        host = url.host
    elif host_match := re.search(r"https?://([^/]+)/", href):
        host = host_match[0]
    else:
        return href

    if "danbooru" in host:
        return "danbooru"
    elif "seiga" in host:
        return "seiga"
    host_split = host.split(".")
    return host_split[1] if len(host_split) >= 3 else host_split[0]


def get_hyperlink(href: str, text: Optional[str] = None) -> str:
    if not text:
        text = get_website_mark(href)
    return href if text == href else f"<a href={href}>{text}</a>"


def get_first_frame_from_video(video: bytes) -> bytes:
    frame = iio.imread(video, index=0, plugin="pyav")
    im = Image.fromarray(frame)
    with BytesIO() as output:
        im.save(output, "JPEG")
        return output.getvalue()


def async_cached(cache, key=hashkey):  # type: ignore
    """
    https://github.com/tkem/cachetools/commit/3f073633ed4f36f05b57838a3e5655e14d3e3524
    """

    def decorator(func):  # type: ignore
        if cache is None:

            async def wrapper(*args, **kwargs):  # type: ignore
                return await func(*args, **kwargs)

        else:

            async def wrapper(*args, **kwargs):  # type: ignore
                k = key(*args, **kwargs)
                with suppress(KeyError):  # key not found
                    return cache[k]
                v = await func(*args, **kwargs)
                with suppress(ValueError):  # value too large
                    cache[k] = v
                return v

        return update_wrapper(wrapper, func)

    return decorator


def parse_cookies(cookies_str: Optional[str] = None) -> dict[str, str]:
    cookies_dict: dict[str, str] = {}
    if cookies_str:
        for line in cookies_str.split(";"):
            key, value = line.strip().split("=", 1)
            cookies_dict[key] = value
    return cookies_dict


def async_lock(
    freq: float = 1,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        call_times: defaultdict[str, arrow.Arrow] = defaultdict(lambda: arrow.now().shift(seconds=-freq))

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            async with locks[func.__name__]:
                last_call_time = call_times[func.__name__]
                elapsed_time = arrow.now() - last_call_time
                if elapsed_time.total_seconds() < freq:
                    await asyncio.sleep(freq - elapsed_time.total_seconds())
                result = await func(*args, **kwargs)
                call_times[func.__name__] = arrow.now()
                return result

        return wrapper

    return decorator


def remove_surrounding_hyphens(text):
    # 查找被连字符包围的内容
    matches = re.finditer(r"(?<!\S)-(.+?)-(?!\S)", text)

    for match in matches:
        extracted_content = match.group(1)
        start, end = match.span()

        # 确保内部没有其他连字符
        if "-" not in extracted_content:
            # 在原字符串中去掉外围的连字符
            text = text[:start] + extracted_content + text[end:]

    return text


def preprocess_search_query(query: str) -> str:
    # 去除外围的连字符
    query = remove_surrounding_hyphens(query)
    query = re.sub(r"(vol|no) (\d+)", r"\1.\2", query, flags=re.IGNORECASE)
    # 替换心形符号为空格
    query = query.replace("♥️", " ")
    # 移除数字相关的内容
    query = re.sub(r"\(C\d+\)", "", query)
    query = re.sub(r"(\S+)x\d+", r"\1", query)
    # query = re.sub(r"\s\d+(\s+)?$", "", query)
    # 移除特殊符号和不需要的文本
    to_remove_patterns = [
        "─",
        "－",
        "~",
        "〜",
        "～",
        "!",
        "！",
        "・",
        "♢",
        "◇",
        "○",
        "●",
        "〇",
        "、",
        ":::",
        "「|」",
        "（|）",
        "＜|＞",
        r"\(|\)",
        r"\[|\]",
        # r"#\d+",
        r"\d+%",
        r"\s+-\s+",
        "[^([]+翻訳",
        "オリジナル",
        "同人誌",
        "成年コミック",
        "雑誌",
        "DL版",
        "ダウンロード版",
        "デジタル版",
    ]
    query = re.sub("|".join(to_remove_patterns), " ", query)

    # 移除孤立的字母和字符
    isolated_chars = [
        r"\b[A-Za-z]\b",  # 英文
        r"\b[\u4e00-\u9fff]\b",  # 中文
        r"\b[\u0400-\u04ff]\b",  # 西里尔字母
        r"\b[\u3040-\u309f\u30a0-\u30ff]\b",  # 日文
    ]
    for pattern in isolated_chars:
        query = re.sub(rf"(?<!-){pattern}(?!-)", "", query)

    return query.strip()


def sort_results_with_ratio(
    res: Union[EHentaiResponse, NHentaiResponse], title: str
) -> Union[list[EHentaiItem], list[NHentaiItem]]:
    raw_with_ratio = [(i, SequenceMatcher(lambda x: x == " ", title, i.title).ratio()) for i in res.raw]
    raw_with_ratio.sort(key=lambda x: x[1], reverse=True)

    return [i[0] for i in raw_with_ratio]


def get_valid_url(url_str: str) -> Optional[URL]:
    try:
        url = URL(url_str)
        if url.host:
            return url
    except Exception:
        return None
    return None


def remove_button(buttons: list[list[MessageButton]], button_data: bytes) -> Optional[list[list[MessageButton]]]:
    for row in buttons:
        for index, button in enumerate(row):
            if button.data == button_data:
                row.pop(index)
                if len(row) == 0:
                    buttons.remove(row)
                return buttons or None
    return buttons


def command(pattern: str, owner_only: bool = False, from_users: Optional[list[int]] = None) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(event: events.NewMessage.Event) -> None:
            if owner_only and event.sender_id != config.owner_id:
                return
            if from_users and event.sender_id not in from_users:
                return

            try:
                await func(event)
            except Exception as e:
                logger.exception(e)
                await event.reply(f"E: {repr(e)}")

        bot.add_event_handler(wrapper, events.NewMessage(from_users=from_users, pattern=pattern))
        return wrapper

    return decorator
