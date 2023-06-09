from httpx import AsyncClient
from PicImageSearch import BaiDu

from . import SEARCH_RESULT_TYPE
from .utils import async_lock, get_bytes_by_url, get_hyperlink


@async_lock()
async def baidu_search(file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    baidu = BaiDu(client=client)
    res = await baidu.search(file=file)
    url = get_hyperlink(res.url)
    if not res.raw:
        return [(f"Baidu 搜索结果为空\nVia: {url}", None)]
    thumbnail = await get_bytes_by_url(res.raw[0].thumbnail)
    res_list = [
        "Baidu 搜索结果",
        get_hyperlink(res.raw[0].url),
        f"Via: {url}",
    ]
    return [("\n".join([i for i in res_list if i]), thumbnail)]
