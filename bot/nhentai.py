import arrow
from httpx import AsyncClient
from lxml.html import HTMLParser, fromstring
from pyquery import PyQuery

from . import SEARCH_RESULT_TYPE
from .config import config
from .nhentai_model import NHentaiItem, NHentaiResponse
from .utils import (
    get_bytes_by_url,
    get_hyperlink,
    parse_cookies,
    preprocess_search_query,
    sort_results_with_ratio,
)

NHENTAI_HEADERS = (
    {
        "User-Agent": config.nhentai_useragent,
    }
    if config.nhentai_cookies and config.nhentai_useragent
    else None
)
NHENTAI_COOKIES = parse_cookies(config.nhentai_cookies)


async def update_nhentai_info(item: NHentaiItem) -> None:
    async with AsyncClient(headers=NHENTAI_HEADERS, cookies=NHENTAI_COOKIES, proxy=config.proxy) as session:
        resp = await session.get(item.url)
        uft8_parser = HTMLParser(encoding="utf-8")
        data = PyQuery(fromstring(resp.text, parser=uft8_parser))
        item.origin = data
        item.title = data.find("h2.title").text() if data.find("h2.title") else data.find("h1.title").text()
        item.type = data.find('#tags a[href^="/category/"] .name').text()
        item.date = data.find("#tags time").attr("datetime")
        item.tags = [i.text() for i in data.find('#tags a:not([href*="/search/?q=pages"]) .name').items()]


async def nhentai_title_search(title: str) -> SEARCH_RESULT_TYPE:
    query = preprocess_search_query(title)
    url = "https://nhentai.net/search/"
    params = {"q": query}
    async with AsyncClient(headers=NHENTAI_HEADERS, cookies=NHENTAI_COOKIES, proxy=config.proxy) as session:
        resp = await session.get(url, params=params)
        if res := NHentaiResponse(resp.text, str(resp.url)):
            # 按搜索关键词相关度排序，相关度越高，结果越靠前
            if res.raw:
                res.raw = sort_results_with_ratio(res, title)
            return await search_result_filter(res)

        return [("NHentai 暂时无法使用", None)]


async def search_result_filter(res: NHentaiResponse) -> SEARCH_RESULT_TYPE:
    url = get_hyperlink(res.url)
    if not res.raw:
        return [(f"NHentai 搜索结果为空\nVia: {url}", None)]

    for i in res.raw:
        await update_nhentai_info(i)

    # 优先找翻译版，没找到就优先找原版
    if config.preferred_language and (
        translated_res := [i for i in res.raw if "translated" in i.tags and config.preferred_language.lower() in i.tags]
    ):
        selected_res = translated_res[0]
    elif not_translated_res := [i for i in res.raw if "translated" not in i.tags]:
        selected_res = not_translated_res[0]
    else:
        selected_res = res.raw[0]

    thumbnail = await get_bytes_by_url(selected_res.thumbnail)
    date = arrow.get(selected_res.date).to("local").format("YYYY-MM-DD HH:mm")
    res_list = [
        "NHentai 搜索结果",
        selected_res.title,
        f"Type：{selected_res.type}",
        f"Date：{date}",
        f"Source：{selected_res.url}",
        f"Via：{url}",
    ]
    return [("\n".join(res_list), thumbnail)]
