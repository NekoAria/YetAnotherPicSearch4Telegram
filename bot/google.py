from base64 import b64decode
from io import BytesIO

from httpx import AsyncClient
from PicImageSearch import Google
from PicImageSearch.model import GoogleResponse

from . import SEARCH_RESULT_TYPE, bot, config
from .utils import async_lock, get_hyperlink


async def send_html_as_file(client, chat, html_content, filename="document.html"):
    html_bytes = html_content.encode("utf-8")
    file = BytesIO(html_bytes)
    file.name = filename
    await client.send_file(chat, file, caption="这是一个 HTML 文件")


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
        # await send_html_as_file(bot, config.owner_id, str(res.origin))
        return [(f"Google 搜索结果为空\nVia: {url}", None)]

    thumbnail = b64decode(selected_res.thumbnail.split(",", 1)[1])
    res_list = [
        "Google 搜索结果",
        selected_res.title,
        f"Source: {get_hyperlink(selected_res.url)}",
        f"Via: {url}",
    ]
    return [("\n".join([i for i in res_list if i]), thumbnail)]
