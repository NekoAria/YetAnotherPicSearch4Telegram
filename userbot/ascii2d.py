from typing import List, Tuple, Union

from aiohttp import ClientSession
from PicImageSearch import Ascii2D
from PicImageSearch.model import Ascii2DResponse

from .config import config
from .utils import DEFAULT_HEADERS, get_hyperlink


async def ascii2d_search(
    file: bytes, client: ClientSession
) -> List[Tuple[str, Union[List[str], str, bytes, None]]]:
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
    ) -> Tuple[str, List[str]]:
        final_res = "Ascii2D 特徴検索結果" if bovw else "Ascii2D 色合検索結果"
        final_res_list = []
        thumbnail_list = []
        separator = "\n----------------------\n"
        selected_res = [i for i in res.raw if i.title or i.url or i.url_list][:3]
        for r in selected_res:
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
            thumbnail_list.append(r.thumbnail)
        final_res += (
            "\n\n"
            + separator.join(final_res_list)
            + f"\n\nVia: {get_hyperlink(res.url)}"
        )
        return final_res, thumbnail_list

    return [await get_final_res(color_res), await get_final_res(bovw_res, True)]
