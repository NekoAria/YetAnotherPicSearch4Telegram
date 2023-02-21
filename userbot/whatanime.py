import math
from typing import Any, Dict

from aiohttp import ClientSession
from PicImageSearch import TraceMoe

from . import SEARCH_RESULT_TYPE, bot
from .utils import get_bytes_by_url


async def whatanime_search(file: bytes, client: ClientSession) -> SEARCH_RESULT_TYPE:
    whatanime = TraceMoe(client=client)
    res = await whatanime.search(file=file)
    if res and res.raw:
        time = res.raw[0].From
        minutes = math.floor(time / 60)
        seconds = math.floor(time % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"
        thumbnail = await get_bytes_by_url(res.raw[0].cover_image)
        video_url = res.raw[0].video
        video = await bot.upload_file(
            await get_bytes_by_url(video_url), file_name="video.mp4"
        )
        chinese_title = res.raw[0].title_chinese
        native_title = res.raw[0].title_native

        start_date = date_to_str(res.raw[0].start_date)
        end_date = ""
        if (end_date_year := res.raw[0].end_date["year"]) and end_date_year > 0:
            end_date = date_to_str(res.raw[0].end_date)
        episode = res.raw[0].episode or 1
        res_list = [
            f"WhatAnime ({res.raw[0].similarity}%)",
            f"Episode {episode} {time_str}",
            native_title,
            chinese_title if chinese_title != native_title else "",
            f"Type: {res.raw[0].type}-{res.raw[0].format}",
            f"Start: {start_date}",
            f"End: {end_date}" if end_date else "",
        ]
        return [("\n".join([i for i in res_list if i]), [thumbnail, video])]

    return [("WhatAnime 暂时无法使用", None)]


def date_to_str(date: Dict[str, Any]) -> str:
    return f"{date['year']}-{date['month']}-{date['day']}"
