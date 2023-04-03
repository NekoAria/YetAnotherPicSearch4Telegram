import re

from httpx import URL, AsyncClient
from PicImageSearch import SauceNAO
from PicImageSearch.model import SauceNAOItem, SauceNAOResponse

from . import SEARCH_RESULT_TYPE, bot
from .config import config
from .ehentai import ehentai_title_search
from .nhentai import nhentai_title_search
from .utils import async_lock, get_bytes_by_url, get_hyperlink, get_source
from .whatanime import whatanime_search

SAUCENAO_DB = {
    "all": 999,
    "pixiv": 5,
    "danbooru": 9,
    "anime": [21, 22],
    "doujin": [18, 38],
    "fakku": 16,
}


@async_lock()
async def saucenao_search(
    file: bytes, client: AsyncClient, mode: str
) -> SEARCH_RESULT_TYPE:
    db = SAUCENAO_DB[mode]
    if isinstance(db, list):
        saucenao = SauceNAO(
            client=client,
            api_key=config.saucenao_api_key,
            dbs=db,
        )
    else:
        saucenao = SauceNAO(
            client=client,
            api_key=config.saucenao_api_key,
            db=db,
        )
    res = await saucenao.search(file=file)

    if (
        res
        and res.status == 429
        and "4 searches every 30 seconds" in res.origin["header"]["message"]
    ):
        return await saucenao_search(file, client, mode)  # type: ignore

    if not res or not res.raw:
        return [("SauceNAO 暂时无法使用", None)]

    selected_res = get_best_result(res, res.raw[0])
    return await get_final_res(file, client, res, selected_res)


def get_best_pixiv_result(
    res: SauceNAOResponse, selected_res: SauceNAOItem
) -> SauceNAOItem:
    pixiv_res_list = list(
        filter(
            lambda x: x.index_id == SAUCENAO_DB["pixiv"]
            and x.url
            and abs(x.similarity - selected_res.similarity) < 5,
            res.raw,
        )
    )
    if len(pixiv_res_list) > 1:
        selected_res = min(
            pixiv_res_list,
            key=lambda x: int(re.search(r"\d+", x.url).group()),  # type: ignore
        )
    return selected_res


def get_best_result(res: SauceNAOResponse, selected_res: SauceNAOItem) -> SauceNAOItem:
    # 如果结果为 pixiv ，尝试找到原始投稿，避免返回盗图者的投稿
    if selected_res.index_id == SAUCENAO_DB["pixiv"]:
        selected_res = get_best_pixiv_result(res, selected_res)
    # 如果地址有多个，优先取 danbooru
    elif len(selected_res.ext_urls) > 1:
        for i in selected_res.ext_urls:
            if "danbooru" in i:
                selected_res.url = i
    return selected_res


async def get_final_res(
    file: bytes,
    client: AsyncClient,
    res: SauceNAOResponse,
    selected_res: SauceNAOItem,
) -> SEARCH_RESULT_TYPE:
    source = selected_res.source if selected_res.source != selected_res.title else ""
    if not source and selected_res.url:
        source = await get_source(selected_res.url)
    if source and URL(source).host:
        source = get_hyperlink(source)

    url = get_hyperlink(selected_res.url)
    author_link = (
        get_hyperlink(selected_res.author_url, selected_res.author)
        if selected_res.author and selected_res.author_url
        else ""
    )

    res_list = [
        f"SauceNAO ({selected_res.similarity}%)",
        selected_res.title,
        f"Author: {author_link}" if author_link else "",
        url if url != source else "",
        f"Source: {source}" if source else "",
        f"Via: {get_hyperlink(res.url)}",
    ]

    final_res: SEARCH_RESULT_TYPE = []

    if res.long_remaining < 10:
        final_res.append((f"SauceNAO 24h 内仅剩 {res.long_remaining} 次使用次数", None))

    thumbnail = await bot.upload_file(
        await get_bytes_by_url(selected_res.thumbnail), file_name="image.jpg"
    )

    final_res.append(("\n".join([i for i in res_list if i]), thumbnail))

    if selected_res.index_id in SAUCENAO_DB["anime"]:  # type: ignore
        final_res.extend(await whatanime_search(file, client))
    elif selected_res.index_id in SAUCENAO_DB["doujin"]:  # type: ignore
        title = selected_res.title.replace("-", "")
        final_res.extend(await search_on_ehentai_and_nhentai(title))
    # 如果搜索结果为 fakku ，额外返回 ehentai 的搜索结果
    elif selected_res.index_id == SAUCENAO_DB["fakku"]:
        title = f"{selected_res.author} {selected_res.title}"
        final_res.extend(await search_on_ehentai_and_nhentai(title))

    return final_res


async def search_on_ehentai_and_nhentai(title: str) -> SEARCH_RESULT_TYPE:
    title_search_result = await ehentai_title_search(title)

    if (
        title_search_result[0][0].startswith("EHentai 搜索结果为空")
        and config.nhentai_useragent
        and config.nhentai_cookies
    ):
        nhentai_title_search_result = await nhentai_title_search(title)
        if not nhentai_title_search_result[0][0].startswith("NHentai 搜索结果为空"):
            title_search_result = nhentai_title_search_result

    return title_search_result
