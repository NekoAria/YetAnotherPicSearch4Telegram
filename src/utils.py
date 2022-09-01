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


def get_hyperlink(text: str, href: str) -> str:
    return f"<a href={href}>{text}</a>"


async def get_first_frame_from_video(video: bytes) -> Optional[bytes]:
    async with ClientSession() as session:
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
        file = d("form > input[type=hidden]").attr("value")
        data = {
            "file": file,
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
        return await get_image_bytes_by_url(first_frame_img_url)
