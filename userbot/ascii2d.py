from io import BytesIO
from typing import List, Tuple

from httpx import AsyncClient
from PicImageSearch import Ascii2D
from PicImageSearch.model import Ascii2DItem, Ascii2DResponse
from PicImageSearch.model.ascii2d import URL
from PIL import Image

from . import SEARCH_RESULT_TYPE
from .utils import (
    async_lock,
    get_bytes_by_url,
    get_hyperlink,
    get_valid_url,
    get_website_mark,
)

SUPPORTED_SOURCES = ["pixiv", "twitter", "fanbox", "fantia", "seiga", "nijie"]


@async_lock()
async def ascii2d_search(file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    ascii2d_color = Ascii2D(client=client)
    color_res = await ascii2d_color.search(file=file)
    if not color_res.raw:
        return [("Ascii2D 暂时无法使用", None)]

    resp_text, resp_url, _ = await ascii2d_color.get(
        color_res.url.replace("/color/", "/bovw/")
    )
    bovw_res = Ascii2DResponse(resp_text, resp_url)

    return [await get_final_res(color_res), await get_final_res(bovw_res, True)]


async def extract_title_and_source_info(raw: Ascii2DItem) -> Tuple[str, str]:
    source = ""
    title = raw.title

    if raw.url_list:
        if title == raw.url_list[0].text:
            title = ""
        if raw.author:
            source_list = build_source_list(raw.url_list)
            source = "\n".join(source_list)
        else:
            source = "  ".join(
                [get_hyperlink(url.href, url.text) for url in raw.url_list]
            )

    if title and get_valid_url(title):
        title = get_hyperlink(title)

    return title, source


def build_source_list(url_list: List[URL]) -> List[str]:
    source_list = []
    for index in range(0, len(url_list), 2):
        url = url_list[index]
        if any(source in url.href for source in SUPPORTED_SOURCES):
            source_list.append(
                f"[{get_website_mark(url.href)}]"
                f" {get_hyperlink(url.href, url.text)} -"
                f" {get_hyperlink(url_list[index + 1].href, url_list[index + 1].text)}"
            )
            continue
        else:
            source_list.append(get_hyperlink(url.href, url.text))
    return source_list


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

        # If thumbnail is in gif format, only take the first frame
        if thumbnail[:3] == b"GIF":
            im = Image.open(BytesIO(thumbnail))
            with BytesIO() as output:
                im.convert("RGB").save(output, "JPEG")
                thumbnail = output.getvalue()

        title, source = await extract_title_and_source_info(r)

        res_list = [r.detail, title, source]
        final_res_list.append("\n".join([i for i in res_list if i]))
        thumbnail_list.append(thumbnail)

        if len(final_res_list) == 3:
            break

    final_res_list_str = separator.join(final_res_list)
    via_link = f"Via: {get_hyperlink(res.url)}"
    final_res += f"\n\n{final_res_list_str}\n\n{via_link}"
    return final_res, thumbnail_list
