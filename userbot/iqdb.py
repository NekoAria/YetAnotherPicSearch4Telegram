from typing import Optional, Tuple

from aiohttp import ClientSession
from PicImageSearch import Iqdb
from yarl import URL

from . import SEARCH_FUNCTION_TYPE, SEARCH_RESULT_TYPE, bot
from .ascii2d import ascii2d_search
from .config import config
from .utils import get_bytes_by_url, get_hyperlink, get_source


async def iqdb_search(
    file: bytes, client: ClientSession
) -> Tuple[SEARCH_RESULT_TYPE, Optional[SEARCH_FUNCTION_TYPE]]:
    iqdb = Iqdb(client=client)
    res = await iqdb.search(file=file)
    if not res.raw:
        return [("Iqdb 暂时无法使用", None)], None
    final_res: SEARCH_RESULT_TYPE = []
    # 如果遇到搜索结果相似度低的情况，去除第一个只有提示信息的空结果
    low_acc = False
    if res.raw[0].content == "No relevant matches":
        low_acc = True
        res.raw.pop(0)
    selected_res = res.raw[0]
    # 优先取 danbooru 或 yande.re
    danbooru_res_list = [i for i in res.raw if i.source == "Danbooru"]
    yandere_res_list = [i for i in res.raw if i.source == "yande.re"]
    if danbooru_res_list:
        selected_res = danbooru_res_list[0]
    elif yandere_res_list:
        selected_res = yandere_res_list[0]
    source = await get_source(selected_res.url)
    if source:
        if URL(source).host:
            source = get_hyperlink(source)
        source = f"Source: {source}"
    res_list = [
        f"Iqdb ({selected_res.similarity}%)",
        get_hyperlink(selected_res.url),
        source,
        f"Via: {get_hyperlink(res.url)}",
    ]
    thumbnail = await bot.upload_file(
        await get_bytes_by_url(selected_res.thumbnail), file_name="image.jpg"
    )
    final_res.append(
        (
            "\n".join([i for i in res_list if i]),
            thumbnail,
        )
    )

    if low_acc and config.auto_use_ascii2d:
        final_res.append((f"相似度 {selected_res.similarity}% 过低，自动使用 Ascii2D 进行搜索", None))
        return final_res, ascii2d_search

    return final_res, None
