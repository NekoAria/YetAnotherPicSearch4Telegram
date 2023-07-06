import itertools
import re
from collections import defaultdict
from typing import Any, Dict

import arrow
from httpx import AsyncClient
from PicImageSearch import EHentai
from PicImageSearch.model import EHentaiResponse
from pyquery import PyQuery

from . import SEARCH_RESULT_TYPE
from .config import config
from .utils import (
    DEFAULT_HEADERS,
    async_lock,
    filter_results_with_ratio,
    get_bytes_by_url,
    get_hyperlink,
    parse_cookies,
    preprocess_search_query,
)


@async_lock(freq=8)
async def ehentai_search(file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    ex = bool(config.exhentai_cookies)
    ehentai = EHentai(client=client)

    if res := await ehentai.search(file=file, ex=ex):
        if "Please wait a bit longer between each file search" in res.origin:
            return await ehentai_search(file, client)

        return await search_result_filter(res)

    return [("EHentai 暂时无法使用", None)]


async def ehentai_title_search(
    title: str,
) -> SEARCH_RESULT_TYPE:
    query = preprocess_search_query(title)
    url = "https://exhentai.org" if config.exhentai_cookies else "https://e-hentai.org"
    params: Dict[str, Any] = {"f_search": query}

    async with AsyncClient(
        headers=DEFAULT_HEADERS,
        cookies=parse_cookies(config.exhentai_cookies),
        proxies=config.proxy,
    ) as session:
        resp = await session.get(url, params=params)
        if res := EHentaiResponse(resp.text, str(resp.url)):
            if not res.raw:
                # 如果第一次没找到，使搜索结果包含被删除的部分，并重新搜索
                params["advsearch"] = 1
                params["f_sname"] = "on"
                params["f_sh"] = "on"
                resp = await session.get(url, params=params)
                res = EHentaiResponse(resp.text, str(resp.url))

            # 只保留标题和搜索关键词相关度较高的结果，并排序，以此来提高准确度
            if res.raw:
                res.raw = filter_results_with_ratio(res, title)
            return await search_result_filter(res)

        return [("EHentai 暂时无法使用", None)]


async def search_result_filter(
    res: EHentaiResponse,
) -> SEARCH_RESULT_TYPE:
    url = get_hyperlink(res.url)
    if not res.raw:
        return [(f"EHentai 搜索结果为空\nVia: {url}", None)]

    # 尝试过滤已删除的
    if not_expunged_res := [
        i for i in res.raw if not PyQuery(i.origin)("[id^='posted'] s")
    ]:
        res.raw = not_expunged_res

    # 尝试过滤无主题的杂图图集
    if not_themeless_res := [i for i in res.raw if "themeless" not in " ".join(i.tags)]:
        res.raw = not_themeless_res

    # 尝试过滤评分低于 3 星的
    if above_3_star_res := [
        i
        for i in res.raw
        if get_star_rating(PyQuery(i.origin)("div.ir").attr("style")) >= 3
    ]:
        res.raw = above_3_star_res

    # 尽可能过滤掉非预期结果(大概
    priority = defaultdict(lambda: 0)
    priority["Image Set"] = 1
    priority["Non-H"] = 2
    priority["Western"] = 3
    priority["Misc"] = 4
    priority["Cosplay"] = 5
    priority["Asian Porn"] = 6
    res.raw.sort(key=lambda x: priority[x.type], reverse=True)
    for key, group in itertools.groupby(res.raw, key=lambda x: x.type):  # type: ignore
        if priority[key] > 0:
            group_list = list(group)
            if len(res.raw) != len(group_list):
                res.raw = [i for i in res.raw if i not in group_list]

    # 优先找翻译版，没找到就优先找原版
    if config.preferred_language and (
        translated_res := [
            i
            for i in res.raw
            if "translated" in " ".join(i.tags)
            and config.preferred_language.lower() in " ".join(i.tags)
        ]
    ):
        selected_res = translated_res[0]
    elif not_translated_res := [
        i for i in res.raw if "translated" not in " ".join(i.tags)
    ]:
        selected_res = not_translated_res[0]
    else:
        selected_res = res.raw[0]

    thumbnail = await get_bytes_by_url(
        selected_res.thumbnail, cookies=config.exhentai_cookies
    )
    date = arrow.get(selected_res.date).to("local").format("YYYY-MM-DD HH:mm")
    favorited = bool(selected_res.origin.find("[id^='posted']").eq(0).attr("style"))
    res_list = [
        "EHentai 搜索结果",
        selected_res.title,
        "❤️ 已收藏" if favorited else "",
        f"Type: {selected_res.type}",
        f"Date: {date}",
        f"Source: {get_hyperlink(selected_res.url)}",
        f"Via: {url}",
    ]
    return [("\n".join([i for i in res_list if i]), thumbnail)]


def get_star_rating(css_style: str) -> float:
    x, y = re.search(r"(-?\d+)px (-\d+)px", css_style).groups()  # type: ignore
    star_rating = 5 - int(x.rstrip("px")) / -16
    if y == "-21px":
        star_rating -= 0.5
    return star_rating
