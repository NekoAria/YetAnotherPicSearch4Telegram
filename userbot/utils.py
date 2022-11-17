from contextlib import suppress
from functools import update_wrapper
from typing import Optional

from aiohttp import ClientSession
from cachetools.keys import hashkey
from pyquery import PyQuery
from yarl import URL

from .config import config

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36"
}


async def get_bytes_by_url(url: str, cookies: Optional[str] = None) -> Optional[bytes]:
    headers = {"Cookie": cookies, **DEFAULT_HEADERS} if cookies else DEFAULT_HEADERS
    async with ClientSession(headers=headers) as session:
        async with session.get(url, proxy=config.proxy) as resp:
            if resp.status == 200 and (image_bytes := await resp.read()):
                return image_bytes
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
    if host := URL(url).host:
        async with ClientSession(headers=DEFAULT_HEADERS) as session:
            if host in ["danbooru.donmai.us", "gelbooru.com"]:
                async with session.get(url, proxy=config.proxy) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        source = PyQuery(html)(".image-container").attr(
                            "data-normalized-source"
                        )
            elif host in ["yande.re", "konachan.com"]:
                async with session.get(url, proxy=config.proxy) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        source = PyQuery(html)("#post_source").attr("value")
                    if not source:
                        source = PyQuery(html)('a[href^="/pool/show/"]').text()

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
    async with ClientSession(headers=DEFAULT_HEADERS) as session:
        resp = await session.post(
            "https://file.io", data={"file": video}, proxy=config.proxy
        )
        link = (await resp.json())["link"]
        resp = await session.get(
            "https://ezgif.com/video-to-jpg",
            params={"url": link},
            proxy=config.proxy,
        )
        d = PyQuery(await resp.text())
        next_url = d("form").attr("action")
        _file = d("form > input[type=hidden]").attr("value")
        data = {
            "file": _file,
            "start": "0",
            "end": "1",
            "size": "original",
            "fps": "10",
        }
        resp = await session.post(
            next_url, params={"ajax": "true"}, data=data, proxy=config.proxy
        )
        d = PyQuery(await resp.text())
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
