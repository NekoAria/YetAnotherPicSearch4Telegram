from typing import List, Tuple

from aiohttp import ClientSession
from PicImageSearch import Ascii2D
from PicImageSearch.model import Ascii2DResponse
from yarl import URL

from . import SEARCH_RESULT_TYPE
from .config import config
from .utils import DEFAULT_HEADERS, get_bytes_by_url, get_hyperlink, get_website_mark


async def ascii2d_search(file: bytes, client: ClientSession) -> SEARCH_RESULT_TYPE:
    ascii2d_color = Ascii2D(client=client)
    color_res = await ascii2d_color.search(file=file)
    if not color_res.raw:
        return [("Ascii2D 暂时无法使用", None)]
    async with ClientSession(headers=DEFAULT_HEADERS) as session:
        resp = await session.get(
            color_res.url.replace("/color/", "/bovw/"), proxy=config.proxy
        )
        bovw_res = Ascii2DResponse(await resp.text(), str(resp.url))

    return [await get_final_res(color_res), await get_final_res(bovw_res, True)]


async def get_final_res(
    res: Ascii2DResponse, bovw: bool = False
) -> Tuple[str, List[bytes]]:
    final_res = "Ascii2D 特徴検索結果" if bovw else "Ascii2D 色合検索結果"
    final_res_list: List[str] = []
    thumbnail_list: List[bytes] = []
    separator = "\n----------------------\n"

    for r in res.raw:
        if not (r.title or r.url_list):
            continue

        if not (thumbnail := await get_bytes_by_url(r.thumbnail)):
            continue

        source = ""
        title = r.title
        if r.url_list:
            if title == r.url_list[0][1]:
                title = ""
            if r.author:
                url_list = r.url_list
                if len(r.url_list) % 2 == 1:
                    url_list, extra = r.url_list[:-1], r.url_list[-1]
                else:
                    extra = None

                source_list = [
                    f"[{get_website_mark(b[0])}] {get_hyperlink(*a)} - {get_hyperlink(*b)}"
                    for a, b in [
                        url_list[i : i + 2] for i in range(0, len(url_list), 2)
                    ]
                ]

                if extra:
                    source_list.append(get_hyperlink(*extra))

                source = "\n".join(source_list)
            else:
                source = "  ".join([get_hyperlink(*i) for i in r.url_list])

        if title and URL(title).host:
            title = get_hyperlink(title)

        res_list = [r.detail, title, source]
        final_res_list.append("\n".join([i for i in res_list if i]))
        thumbnail_list.append(thumbnail)

        if len(final_res_list) == 3:
            break

    final_res_list_str = separator.join(final_res_list)
    via_link = f"Via: {get_hyperlink(res.url)}"
    final_res += f"\n\n{final_res_list_str}\n\n{via_link}"
    return final_res, thumbnail_list
