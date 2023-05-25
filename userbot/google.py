from base64 import b64decode

from httpx import AsyncClient
from PicImageSearch import Google
from PicImageSearch.model import GoogleResponse

from . import SEARCH_RESULT_TYPE
from .utils import async_lock, get_hyperlink


@async_lock()
async def google_search(file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    google = Google(client=client)
    if res := await google.search(file=file):
        return await search_result_filter(res)
    return [("Google 暂时无法使用", None)]


async def search_result_filter(
    res: GoogleResponse,
) -> SEARCH_RESULT_TYPE:
    url = get_hyperlink(res.url)
    if not res.raw:
        return [(f"Google 搜索结果为空\nVia: {url}", None)]

    selected_res = next((i for i in res.raw if i.thumbnail), res.raw[0])
    if not selected_res.thumbnail:
        return [(f"Google 搜索结果为空\nVia: {url}", None)]

    thumbnail = b64decode(selected_res.thumbnail.split(",", 1)[1])
    res_list = [
        "Google 搜索结果",
        selected_res.title,
        f"Source: {get_hyperlink(selected_res.url)}",
        f"Via: {url}",
    ]
    return [("\n".join([i for i in res_list if i]), thumbnail)]
