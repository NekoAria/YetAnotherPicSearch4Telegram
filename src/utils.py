from typing import Optional

from aiohttp import ClientSession
from pyquery import PyQuery
from yarl import URL

from .config import config


async def get_image_bytes_by_url(
    url: str, cookies: Optional[str] = None
) -> Optional[bytes]:
    headers = {"Cookie": cookies} if cookies else None
    async with ClientSession(headers=headers) as session:
        async with session.get(url, proxy=config.proxy) as resp:
            if resp.status == 200 and (image_bytes := await resp.read()):
                return image_bytes
    return None


async def get_source(url: str) -> str:
    source = ""
    async with ClientSession() as session:
        if URL(url).host in ["danbooru.donmai.us", "gelbooru.com"]:
            async with session.get(url, proxy=config.proxy) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    source = PyQuery(html)(".image-container").attr(
                        "data-normalized-source"
                    )
        elif URL(url).host in ["yande.re", "konachan.com"]:
            async with session.get(url, proxy=config.proxy) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    source = PyQuery(html)("#post_source").attr("value")
    return source
