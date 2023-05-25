from httpx import AsyncClient
from PicImageSearch import Yandex
from PicImageSearch.model import YandexResponse

from . import SEARCH_RESULT_TYPE
from .utils import async_lock, get_bytes_by_url, get_hyperlink


@async_lock()
async def yandex_search(file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    yandex = Yandex(client=client)
    if res := await yandex.search(file=file):
        return await search_result_filter(res)
    return [("Yandex 暂时无法使用", None)]


async def search_result_filter(
    res: YandexResponse,
) -> SEARCH_RESULT_TYPE:
    url = get_hyperlink(res.url)
    if not res.raw:
        return [(f"Yandex 搜索结果为空\nVia: {url}", None)]

    thumbnail = await get_bytes_by_url(res.raw[0].thumbnail)
    res_list = [
        "Yandex 搜索结果",
        res.raw[0].size,
        res.raw[0].title,
        res.raw[0].source,
        res.raw[0].content,
        f"Source: {get_hyperlink(res.raw[0].url)}",
        f"Via: {url}",
    ]
    return [("\n".join([i for i in res_list if i]), thumbnail)]
