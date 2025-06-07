from httpx import AsyncClient
from PicImageSearch import Iqdb

from . import SEARCH_RESULT_TYPE
from .utils import (
    async_lock,
    get_bytes_by_url,
    get_hyperlink,
    get_source,
    get_valid_url,
)


@async_lock()
async def iqdb_search(file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    iqdb = Iqdb(client=client)
    res = await iqdb.search(file=file)
    if not res.raw:
        return [("Iqdb 暂时无法使用", None)]

    final_res: SEARCH_RESULT_TYPE = []
    # 如果遇到搜索结果相似度低的情况，去除第一个只有提示信息的空结果
    if res.raw[0].content == "No relevant matches":
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
        if get_valid_url(source):
            source = get_hyperlink(source)
        source = f"Source: {source}"
    res_list = [
        f"Iqdb ({selected_res.similarity}%)",
        get_hyperlink(selected_res.url),
        source,
        f"Via: {get_hyperlink(res.url)}",
    ]
    thumbnail = await get_bytes_by_url(selected_res.thumbnail)
    final_res.append(("\n".join([i for i in res_list if i]), thumbnail))

    return final_res
