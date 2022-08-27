from typing import List, Optional, Tuple

from aiohttp import ClientSession
from PicImageSearch import Ascii2D
from PicImageSearch.model import Ascii2DResponse

from .utils import get_image_bytes_by_url


async def ascii2d_search(
    file: bytes, client: ClientSession
) -> List[Tuple[str, Optional[bytes]]]:
    ascii2d_color = Ascii2D(client=client)
    ascii2d_bovw = Ascii2D(bovw=True, client=client)
    color_res = await ascii2d_color.search(file=file)
    if not color_res or not color_res.raw:
        return [("Ascii2D 暂时无法使用", None)]
    bovw_res = await ascii2d_bovw.search(file=file)

    async def get_final_res(res: Ascii2DResponse) -> Tuple[List[str], Optional[bytes]]:
        if not res.raw[0].url:
            res.raw[0] = res.raw[1]
        thumbnail = await get_image_bytes_by_url(res.raw[0].thumbnail)
        _url = res.raw[0].url if res.raw[0] else ""
        res_list = [
            res.raw[0].title or "",
            f"作者：{res.raw[0].author}" if res.raw[0].author else "",
            f"[来源]({_url})" if _url else "",
            f"[搜索页面]({res.url})",
        ]
        return [i for i in res_list if i != ""], thumbnail

    color_final_res = await get_final_res(color_res)
    bovw_final_res = await get_final_res(bovw_res)
    if color_final_res[0][:-1] == bovw_final_res[0][:-1]:
        return [
            (
                "Ascii2D 色合検索与特徴検索結果完全一致\n" + "\n".join(color_final_res[0]),
                color_final_res[1],
            )
        ]

    return [
        (
            f"Ascii2D 色合検索結果\n" + "\n".join(color_final_res[0]),
            color_final_res[1],
        ),
        (
            f"Ascii2D 特徴検索結果\n" + "\n".join(bovw_final_res[0]),
            bovw_final_res[1],
        ),
    ]
