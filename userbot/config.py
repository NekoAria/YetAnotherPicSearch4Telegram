from typing import List, Optional

from pydantic import BaseSettings


class Config(BaseSettings):

    # telegram bot token
    token: str = ""
    # telegram bot 拥有者 id
    owner_id: int = 0
    # 允许使用这个 bot 的用户 id 列表
    allowed_users: List[int] = []
    # 允许使用这个 bot 的群组或频道列表
    allowed_chats: List[int] = []
    # 大部分请求所使用的代理: http://
    proxy: Optional[str] = None
    # telegram api id
    api_id: int = 1025907  # get it from https://core.telegram.org/api/obtaining_api_id
    # telegram api hash
    api_hash: str = "452b0359b988148995f22ff0f4229750"  # get it from https://core.telegram.org/api/obtaining_api_hash
    # saucenao 相似度低于这个百分比将被认定为相似度过低
    saucenao_low_acc: int = 60
    # saucenao APIKEY，必填，否则无法使用 saucenao 搜图
    saucenao_api_key: str = ""
    # exhentai cookies，选填，没有的情况下自动改用 e-hentai 搜图
    exhentai_cookies: str = ""


config = Config(_env_file=".env", _env_file_encoding="utf-8")
