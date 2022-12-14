import re
from asyncio import sleep
from typing import Optional, Tuple

from aiohttp import ClientSession
from PicImageSearch import SauceNAO
from yarl import URL

from . import SEARCH_FUNCTION_TYPE, SEARCH_RESULT_TYPE, bot
from .config import config
from .ehentai import ehentai_title_search
from .utils import get_bytes_by_url, get_hyperlink, get_source
from .whatanime import whatanime_search


async def saucenao_search(
    file: bytes, client: ClientSession, mode: str
) -> Tuple[SEARCH_RESULT_TYPE, Optional[SEARCH_FUNCTION_TYPE]]:
    saucenao_db = {
        "all": 999,
        "pixiv": 5,
        "danbooru": 9,
        "anime": [21, 22],
        "doujin": [18, 38],
    }
    if isinstance(db := saucenao_db[mode], list):
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
    final_res: SEARCH_RESULT_TYPE = []
    if res and res.raw:
        selected_res = res.raw[0]
        # 如果结果为 pixiv ，尝试找到原始投稿，避免返回盗图者的投稿
        if selected_res.index_id == saucenao_db["pixiv"]:
            pixiv_res_list = list(
                filter(
                    lambda x: x.index_id == saucenao_db["pixiv"]
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
        # 如果地址有多个，优先取 danbooru
        elif len(selected_res.ext_urls) > 1:
            for i in selected_res.ext_urls:
                if "danbooru" in i:
                    selected_res.url = i
        source = selected_res.source
        if source and source == selected_res.title:
            source = ""
        if not source and selected_res.url:
            source = await get_source(selected_res.url)
        if source and URL(source).host:
            source = get_hyperlink(source)
        author = selected_res.author
        if author and selected_res.author_url:
            author = get_hyperlink(selected_res.author_url, author)
        res_list = [
            f"SauceNAO ({selected_res.similarity}%)",
            selected_res.title,
            f"Author: {author}" if author else "",
            f"Source: {source}" if source else "",
            f"Via: {get_hyperlink(res.url)}",
        ]
        if res.long_remaining < 10:
            final_res.append((f"SauceNAO 24h 内仅剩 {res.long_remaining} 次使用次数", None))
        thumbnail = await bot.upload_file(
            await get_bytes_by_url(selected_res.thumbnail), file_name="image.jpg"
        )
        final_res.append(("\n".join([i for i in res_list if i]), thumbnail))
        if selected_res.index_id in saucenao_db["anime"]:  # type: ignore
            return final_res, whatanime_search
        elif selected_res.index_id in saucenao_db["doujin"]:  # type: ignore
            title = selected_res.title.replace("-", "")
            final_res.extend(await ehentai_title_search(title))
    elif (
        res
        and res.status == 429
        and "4 searches every 30 seconds" in res.origin["header"]["message"]
    ):
        await sleep(30 / 4)
        return await saucenao_search(file, client, mode)
    else:
        final_res.append(("SauceNAO 暂时无法使用", None))
    return final_res, None
