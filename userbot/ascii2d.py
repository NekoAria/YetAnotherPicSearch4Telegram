from typing import List, Tuple, Union

from aiohttp import ClientSession
from PicImageSearch import Ascii2D
from PicImageSearch.model import Ascii2DResponse

from .config import config
from .utils import DEFAULT_HEADERS, get_hyperlink, get_image_bytes_by_url


async def ascii2d_search(
    file: bytes, client: ClientSession
) -> List[Tuple[str, Union[List[str], List[bytes], str, bytes, None]]]:
    ascii2d_color = Ascii2D(client=client)
    color_res = await ascii2d_color.search(file=file)
    if not color_res.raw:
        return [("Ascii2D 暂时无法使用", None)]
    async with ClientSession(headers=DEFAULT_HEADERS) as session:
        resp = await session.get(
            color_res.url.replace("/color/", "/bovw/"), proxy=config.proxy
        )
        bovw_res = Ascii2DResponse(await resp.text(), str(resp.url))

    async def get_final_res(
        res: Ascii2DResponse, bovw: bool = False
    ) -> Tuple[str, List[bytes]]:
        final_res = "Ascii2D 特徴検索結果" if bovw else "Ascii2D 色合検索結果"
        final_res_list: List[str] = []
        thumbnail_list: List[bytes] = []
        separator = "\n----------------------\n"
        for r in res.raw:
            if len(final_res_list) == 3:
                break
            if not (r.title or r.url or r.url_list):
                continue
            if (thumbnail := await get_image_bytes_by_url(r.thumbnail)) is None:
                continue
            author = r.author
            if author and r.author_url:
                author = get_hyperlink(r.author_url, author)
            source = None
            if r.url:
                source = f"Source: {get_hyperlink(r.url)}"
            elif r.url_list:
                source = "  ".join([get_hyperlink(*i) for i in r.url_list])
            res_list = [
                r.detail,
                r.title,
                f"Author: {author}" if author else "",
                source,
            ]
            final_res_list.append("\n".join([i for i in res_list if i]))
            thumbnail_list.append(thumbnail)
        final_res += (
            "\n\n"
            + separator.join(final_res_list)
            + f"\n\nVia: {get_hyperlink(res.url)}"
        )
        return final_res, thumbnail_list

    return [await get_final_res(color_res), await get_final_res(bovw_res, True)]
