import re
from asyncio import sleep
from typing import List, Tuple, Union

from aiohttp import ClientSession
from PicImageSearch import SauceNAO
from yarl import URL

from .ascii2d import ascii2d_search
from .config import config
from .ehentai import ehentai_title_search
from .utils import get_hyperlink, get_image_bytes_by_url, get_source
from .whatanime import whatanime_search


async def saucenao_search(
    file: bytes, client: ClientSession, mode: str
) -> List[Tuple[str, Union[str, bytes, None]]]:
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
    final_res: List[Tuple[str, Union[str, bytes, None]]] = []
    if res and res.raw:
        selected_res = res.raw[0]
        ext_urls = selected_res.origin["data"].get("ext_urls")
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
        elif ext_urls and len(ext_urls) > 1:
            for i in ext_urls:
                if "danbooru" in i:
                    selected_res.url = i
        thumbnail = await get_image_bytes_by_url(selected_res.thumbnail)
        if selected_res.origin["data"].get("source"):
            source = selected_res.origin["data"]["source"]
        else:
            source = await get_source(selected_res.url)
        if source:
            if URL(source).host:
                source = get_hyperlink("来源", source)
            else:
                source = f"来源：{source}"
        # 如果结果为 doujin ，尝试返回日文标题而不是英文标题
        if selected_res.index_id in saucenao_db["doujin"]:  # type: ignore
            if title := (
                selected_res.origin["data"].get("jp_name")
                or selected_res.origin["data"].get("eng_name")
            ):
                selected_res.title = title
        author = selected_res.author
        if author and selected_res.index_id == saucenao_db["pixiv"]:
            author = get_hyperlink(
                author,
                f'https://www.pixiv.net/users/{selected_res.origin["data"]["member_id"]}',
            )
        res_list = [
            f"SauceNAO（{selected_res.similarity}%）",
            selected_res.title,
            f"作者：{author}" if author else "",
            selected_res.url,
            source,
        ]
        if res.long_remaining < 10:
            final_res.append((f"SauceNAO 24h 内仅剩 {res.long_remaining} 次使用次数", None))
        final_res.append(("\n".join([i for i in res_list if i != ""]), thumbnail))
        if selected_res.similarity < config.saucenao_low_acc:
            # 因为 saucenao 的动画搜索数据库更新不够快，所以当搜索模式为动画时额外增加 whatanime 的搜索结果
            if mode == "anime":
                final_res.extend(await whatanime_search(file, client))
            elif config.use_ascii2d_when_low_acc:
                final_res.append(
                    (f"相似度 {selected_res.similarity}% 过低，自动使用 Ascii2D 进行搜索", None)
                )
                final_res.extend(await ascii2d_search(file, client))
        elif selected_res.index_id in saucenao_db["doujin"]:  # type: ignore
            final_res.extend(await ehentai_title_search(selected_res.title))
        elif selected_res.index_id in saucenao_db["anime"]:  # type: ignore
            final_res.extend(await whatanime_search(file, client))
    elif (
        res
        and res.status == 429
        and "4 searches every 30 seconds" in res.origin["header"]["message"]
    ):
        await sleep(30 / 4)
        return await saucenao_search(file, client, mode)
    else:
        final_res.append(("SauceNAO 暂时无法使用，自动使用 Ascii2D 进行搜索", None))
        final_res.extend(await ascii2d_search(file, client))
    return final_res
