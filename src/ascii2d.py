from typing import List, Optional, Tuple

from aiohttp import ClientSession
from PicImageSearch import Ascii2D
from PicImageSearch.model import Ascii2DResponse

from .config import config
from .utils import get_hyperlink, get_image_bytes_by_url


async def ascii2d_search(
    file: bytes, client: ClientSession
) -> List[Tuple[str, Optional[bytes]]]:
    ascii2d_color = Ascii2D(client=client)
    color_res = await ascii2d_color.search(file=file)
    if not color_res or not color_res.raw:
        return [("Ascii2D 暂时无法使用", None)]
    async with ClientSession() as session:
        resp = await session.get(
            color_res.url.replace("/color/", "/bovw/"), proxy=config.proxy
        )
        bovw_res = Ascii2DResponse(await resp.text(), str(resp.url))

    async def get_final_res(res: Ascii2DResponse) -> Tuple[List[str], Optional[bytes]]:
        selected_res = [i for i in res.raw if i.title or i.url][0]
        thumbnail = await get_image_bytes_by_url(selected_res.thumbnail)
        author = selected_res.author
        if author and selected_res.author_url:
            author = get_hyperlink(author, selected_res.author_url)
        res_list = [
            selected_res.title,
            f"作者：{author}" if author else "",
            get_hyperlink("来源", selected_res.url) if selected_res.url else "",
            get_hyperlink("搜索页面", res.url),
        ]
        return [i for i in res_list if i != ""], thumbnail

    color_final_res, color_thumbnail = await get_final_res(color_res)
    bovw_final_res, bovw_thumbnail = await get_final_res(bovw_res)
    if color_final_res[:-1] == bovw_final_res[:-1]:
        return [
            (
                "Ascii2D 色合検索与特徴検索結果完全一致\n" + "\n".join(color_final_res),
                color_thumbnail,
            )
        ]

    return [
        (
            f"Ascii2D 色合検索結果\n" + "\n".join(color_final_res),
            color_thumbnail,
        ),
        (
            f"Ascii2D 特徴検索結果\n" + "\n".join(bovw_final_res),
            bovw_thumbnail,
        ),
    ]
