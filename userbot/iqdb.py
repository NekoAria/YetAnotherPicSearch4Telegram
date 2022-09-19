from typing import List, Tuple, Union

from aiohttp import ClientSession
from PicImageSearch import Iqdb
from yarl import URL

from .ascii2d import ascii2d_search
from .config import config
from .utils import get_hyperlink, get_source


async def iqdb_search(
    file: bytes, client: ClientSession
) -> List[Tuple[str, Union[List[str], List[bytes], str, bytes, None]]]:
    iqdb = Iqdb(client=client)
    res = await iqdb.search(file=file)
    if not res.raw:
        return [("Iqdb 暂时无法使用", None)]
    final_res: List[Tuple[str, Union[List[str], List[bytes], str, bytes, None]]] = []
    # 如果遇到搜索结果相似度低的情况，去除第一个只有提示信息的空结果
    low_acc = False
    if res.raw[0].content == "No relevant matches":
        low_acc = True
        res.raw.pop(0)
    selected_res = res.raw[0]
    # 优先取 danbooru 或 yande.re
    danbooru_res_list = [i for i in res.raw if i.source == "Danbooru"]
    yandere_res_list = [i for i in res.raw if i.source == "yande.re"]
    if danbooru_res_list:
        selected_res = danbooru_res_list[0]
    elif yandere_res_list:
        selected_res = yandere_res_list[0]
    source = await get_source(selected_res.url)
    if source:
        if URL(source).host:
            source = get_hyperlink(source)
        source = f"Source: {source}"
    res_list = [
        f"Iqdb ({selected_res.similarity}%)",
        get_hyperlink(selected_res.url),
        source,
    ]
    final_res.append(
        (
            "\n".join([i for i in res_list if i]),
            selected_res.thumbnail,
        )
    )

    if low_acc and config.auto_use_ascii2d:
        final_res.append((f"相似度 {selected_res.similarity}% 过低，自动使用 Ascii2D 进行搜索", None))
        final_res.extend(await ascii2d_search(file, client))

    return final_res
