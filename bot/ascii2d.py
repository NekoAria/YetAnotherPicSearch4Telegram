import re
from io import BytesIO

from httpx import AsyncClient
from loguru import logger
from PicImageSearch import Ascii2D
from PicImageSearch.model import Ascii2DItem, Ascii2DResponse
from PicImageSearch.model.ascii2d import URL
from PIL import Image

from . import SEARCH_RESULT_TYPE, config
from .utils import (
    SEPARATOR,
    async_lock,
    get_bytes_by_url,
    get_hyperlink,
    get_valid_url,
    get_website_mark,
)

SUPPORTED_SOURCES = [
    "fanbox",
    "fantia",
    "misskey",
    "nijie",
    "pixiv",
    "seiga",
    "twitter",
]


@async_lock()
async def ascii2d_search(file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    ascii2d_color = Ascii2D(base_url=config.ascii2d_base_url, client=client)
    color_res = await ascii2d_color.search(file=file)
    if not color_res.raw:
        logger.info(color_res.origin)
        return [("Ascii2D 暂时无法使用", None)]

    resp_text, resp_url, _ = await ascii2d_color.get(re.sub(r"(/|%2F)color", r"\1bovw", color_res.url))
    bovw_res = Ascii2DResponse(resp_text, resp_url)
    # 去除 bovw_res 中已经存在于 color_res 的部分
    color_res_origin_list = [str(i.origin) for i in color_res.raw]
    duplicated_raw = [
        i for i in bovw_res.raw if (str(i.origin) in color_res_origin_list and any(i.title or i.url_list))
    ]
    duplicated_count = len(duplicated_raw)
    bovw_res.raw = [i for i in bovw_res.raw if i not in duplicated_raw]

    return [await get_final_res(color_res), await get_final_res(bovw_res, True, duplicated_count)]


async def extract_title_and_source_info(raw: Ascii2DItem) -> tuple[str, str]:
    source = ""
    title = raw.title

    if raw.url_list:
        if title == raw.url_list[0].text:
            title = ""
        if raw.author:
            source_list = build_source_list(raw.url_list)
            source = "\n".join(source_list)
        else:
            source = "  ".join([get_hyperlink(url.href, url.text) for url in raw.url_list])

    if title and get_valid_url(title):
        title = get_hyperlink(title)

    return title, source


def build_source_list(url_list: list[URL]) -> list[str]:
    source_list = []
    first_url = url_list[0]
    if "getchu" in first_url.href:
        source_list.extend(f"[getchu] {get_hyperlink(url.href, url.text)}" for url in url_list)
        return source_list

    index = 0
    while index < len(url_list):
        url = url_list[index]
        if any(source in url.href for source in SUPPORTED_SOURCES):
            source_list.append(
                f"[{get_website_mark(url.href)}]"
                f" {get_hyperlink(url.href, url.text)} -"
                f" {get_hyperlink(url_list[index + 1].href, url_list[index + 1].text)}"
            )
            index += 1
        else:
            source_list.append(get_hyperlink(url.href, url.text))

        index += 1

    return source_list


async def get_final_res(res: Ascii2DResponse, bovw: bool = False, duplicated_count: int = 0) -> tuple[str, list[bytes]]:
    final_res = "Ascii2D 特徴検索結果" if bovw else "Ascii2D 色合検索結果"
    if duplicated_count:
        final_res += f" (已去除与特徴検索結果重复的 {duplicated_count} 个结果)"
    final_res_list: list[str] = []
    thumbnail_list: list[bytes] = []

    for r in res.raw:
        if not (r.title or r.url_list):
            continue

        # TODO: 修改 PicImageSearch 中的 ascii2d model 中的 thumbnail 赋值逻辑，重点是其 host
        # thumbnail = await get_bytes_by_url(r.thumbnail)
        thumbnail = await get_bytes_by_url(r.thumbnail.replace("https://ascii2d.net", config.ascii2d_base_url))

        # If thumbnail is in gif format, only take the first frame
        if thumbnail and thumbnail[:3] == b"GIF":
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

    final_res_list_str = SEPARATOR.join(final_res_list)
    via_link = f"Via: {get_hyperlink(res.url)}"
    final_res += f"\n\n{final_res_list_str}\n\n{via_link}"
    return final_res, thumbnail_list
