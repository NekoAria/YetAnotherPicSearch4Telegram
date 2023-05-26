import asyncio
import re
from collections import defaultdict
from contextlib import suppress
from difflib import SequenceMatcher
from functools import update_wrapper, wraps
from typing import (
    Any,
    Callable,
    Coroutine,
    DefaultDict,
    Dict,
    List,
    Optional,
    TypeVar,
    Union,
)

import arrow
from cachetools.keys import hashkey
from httpx import URL, AsyncClient
from PicImageSearch.model.ehentai import EHentaiItem, EHentaiResponse
from pyquery import PyQuery

from .config import config
from .nhentai_model import NHentaiItem, NHentaiResponse

T = TypeVar("T")
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/99.0.4844.82 Safari/537.36"
    )
}


async def get_bytes_by_url(url: str, cookies: Optional[str] = None) -> Optional[bytes]:
    async with AsyncClient(
        headers=DEFAULT_HEADERS,
        cookies=parse_cookies(cookies),
        proxies=config.proxy,
        follow_redirects=True,
    ) as session:
        resp = await session.get(url)
        if resp.status_code < 400:
            return resp.content
    return None


def handle_source(source: str) -> str:
    return (
        source.replace("www.pixiv.net/en/artworks", "www.pixiv.net/artworks")
        .replace(
            "www.pixiv.net/member_illust.php?mode=medium&illust_id=",
            "www.pixiv.net/artworks/",
        )
        .replace("http://", "https://")
    )


async def get_source(url: str) -> str:
    source = url
    if host := URL(source).host:
        headers = None if host == "danbooru.donmai.us" else DEFAULT_HEADERS
        async with AsyncClient(
            headers=headers, proxies=config.proxy, follow_redirects=True
        ) as session:
            resp = await session.get(source)
            if resp.status_code >= 400:
                return ""

            if host in ["danbooru.donmai.us", "gelbooru.com"]:
                source = PyQuery(resp.text)(".image-container").attr(
                    "data-normalized-source"
                )

            elif host in ["yande.re", "konachan.com"]:
                source = PyQuery(resp.text)("#post_source").attr("value")
                if not source:
                    source = PyQuery(resp.text)('a[href^="/pool/show/"]').text()

    return handle_source(source) if (source and URL(source).host) else (source or "")


def get_website_mark(href: str) -> str:
    host = URL(href).host
    if not host:
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


async def get_first_frame_from_video(video: bytes) -> Optional[bytes]:
    async with AsyncClient(
        headers=DEFAULT_HEADERS, proxies=config.proxy, follow_redirects=True
    ) as session:
        resp = await session.post("https://file.io", files={"file": video})
        link = resp.json()["link"]
        resp = await session.get("https://ezgif.com/video-to-jpg", params={"url": link})
        d = PyQuery(resp.text)
        next_url = d("form").attr("action")
        _file = d("form > input[type=hidden]").attr("value")
        data = {
            "file": _file,
            "start": "0",
            "end": "1",
            "size": "original",
            "fps": "10",
        }
        resp = await session.post(next_url, params={"ajax": "true"}, data=data)
        d = PyQuery(resp.text)
        first_frame_img_url = "https:" + d("img:nth-child(1)").attr("src")
        return await get_bytes_by_url(first_frame_img_url)


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


def parse_cookies(cookies_str: Optional[str] = None) -> Dict[str, str]:
    cookies_dict: Dict[str, str] = {}
    if cookies_str:
        for line in cookies_str.split(";"):
            key, value = line.strip().split("=", 1)
            cookies_dict[key] = value
    return cookies_dict


def async_lock(
    freq: float = 1,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]
]:
    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]]
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        locks: DefaultDict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        call_times: DefaultDict[str, arrow.Arrow] = defaultdict(
            lambda: arrow.now().shift(seconds=-freq)
        )

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


def preprocess_search_query(query: str) -> str:
    query = re.sub(r"●|・|~|～|〜|、|×|:::|\s+-\s+|\[中国翻訳]", " ", query)
    # 去除独立的英文、日文、中文字符，但不去除带连字符的
    for i in [
        r"\b[A-Za-z]\b",
        r"\b[\u4e00-\u9fff]\b",
        r"\b[\u3040-\u309f\u30a0-\u30ff]\b",
    ]:
        query = re.sub(rf"(?<!-){i}(?!-)", "", query)

    return query.strip()


def filter_results_with_ratio(
    res: Union[EHentaiResponse, NHentaiResponse], title: str
) -> Union[List[EHentaiItem], List[NHentaiItem]]:
    raw_with_ratio = [
        (i, SequenceMatcher(lambda x: x == " ", title, i.title).ratio())
        for i in res.raw
    ]
    raw_with_ratio.sort(key=lambda x: x[1], reverse=True)

    if filtered := [i[0] for i in raw_with_ratio if i[1] > 0.65]:
        return filtered

    return [i[0] for i in raw_with_ratio]
