import itertools
import re
from collections import defaultdict
from typing import Any

import arrow
from httpx import AsyncClient
from loguru import logger
from PicImageSearch import EHentai
from PicImageSearch.model import EHentaiResponse
from pyquery import PyQuery

from . import SEARCH_RESULT_TYPE
from .config import config
from .utils import (
    DEFAULT_HEADERS,
    async_lock,
    get_bytes_by_url,
    get_hyperlink,
    parse_cookies,
    preprocess_search_query,
    sort_results_with_ratio,
)


@async_lock(freq=8)
async def ehentai_search(file: bytes, client: AsyncClient) -> SEARCH_RESULT_TYPE:
    is_ex = bool(config.exhentai_cookies)
    ehentai = EHentai(client=client, is_ex=is_ex)

    max_retries = 3
    retries = 0

    while retries < max_retries:
        if res := await ehentai.search(file=file):
            logger.info(res.url)
            if res.url == "https://exhentai.org/upld/image_lookup.php":
                logger.warning("Please wait a bit longer between each file search.")
                retries += 1
                continue
            return await search_result_filter(res)

        return [("EHentai 暂时无法使用", None)]

    return [("EHentai 搜索超时，请稍后重试", None)]


async def ehentai_title_search(
    title: str,
) -> SEARCH_RESULT_TYPE:
    url = "https://exhentai.org" if config.exhentai_cookies else "https://e-hentai.org"
    query = preprocess_search_query(title)
    params: dict[str, Any] = {"f_search": query}

    async with AsyncClient(
        headers=DEFAULT_HEADERS,
        cookies=parse_cookies(config.exhentai_cookies),
        proxy=config.proxy,
    ) as session:
        resp = await session.get(url, params=params)
        if res := EHentaiResponse(resp.text, str(resp.url)):
            if not res.raw:
                # 禁用自定义过滤器，并重新搜索
                params["f_sft"] = "on"
                params["f_sfu"] = "on"
                params["f_sfl"] = "on"
                resp = await session.get(url, params=params)
                res = EHentaiResponse(resp.text, str(resp.url))

            if not res.raw:
                # 使搜索结果包含被删除的部分，并重新搜索
                params["advsearch"] = 1
                params["f_sname"] = "on"
                params["f_sh"] = "on"
                resp = await session.get(url, params=params)
                res = EHentaiResponse(resp.text, str(resp.url))

            # 按搜索关键词相关度排序，相关度越高，结果越靠前
            if res.raw:
                res.raw = sort_results_with_ratio(res, title)
            return await search_result_filter(res)

        return [("EHentai 暂时无法使用", None)]


async def search_result_filter(
    res: EHentaiResponse,
) -> SEARCH_RESULT_TYPE:
    url = get_hyperlink(res.url)
    if not res.raw:
        return [(f"EHentai 搜索结果为空\nVia: {url}", None)]

    # 尝试过滤已删除的
    if not_expunged_res := [i for i in res.raw if not PyQuery(i.origin)("[id^='posted'] s")]:
        res.raw = not_expunged_res

    # 尝试过滤无主题的杂图图集
    if not_themeless_res := [i for i in res.raw if "themeless" not in " ".join(i.tags)]:
        res.raw = not_themeless_res

    # 尝试过滤评分低于 3 星的
    if above_3_star_res := [i for i in res.raw if get_star_rating(PyQuery(i.origin)("div.ir").attr("style")) >= 3]:
        res.raw = above_3_star_res

    # 检查是否所有结果的 type 都相同
    types = {i.type for i in res.raw}
    if len(types) > 1:
        # 尽可能过滤掉非预期结果 (大概
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

    selected_res = res.raw[0]
    # 优先找选集或单行本
    if anthology_or_tankoubon_res := [
        i
        for i in res.raw
        if ("anthology" in " ".join(i.tags) or "tankoubon" in " ".join(i.tags))
        and ("incomplete" not in " ".join(i.tags))
    ]:
        res.raw = anthology_or_tankoubon_res

    # 其次优先找翻译版或源语言为偏好语言的，没找到就优先找原版
    if config.preferred_language and (
        preferred_language_res := [i for i in res.raw if f"language:{config.preferred_language.lower()}" in i.tags]
    ):
        selected_res = preferred_language_res[0]
    elif not_translated_res := [i for i in res.raw if "translated" not in " ".join(i.tags)]:
        # 尝试过滤无作者的结果
        if len(types) == 1:
            found_artist = False
            for i in not_translated_res:
                if any(tag.startswith("artist:") for tag in i.tags):
                    selected_res = i
                    found_artist = True
                    break
            if not found_artist:
                selected_res = not_translated_res[0]
        else:
            selected_res = not_translated_res[0]

    thumbnail = await get_bytes_by_url(selected_res.thumbnail, cookies=config.exhentai_cookies)
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
