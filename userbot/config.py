from typing import Any, List, Optional

from pydantic import BaseSettings, validator


class Config(BaseSettings):
    # telegram bot token
    token: str
    # telegram bot 拥有者 id
    owner_id: int
    # 允许使用这个 bot 的用户 id 列表
    allowed_users: List[int] = []
    # 允许使用这个 bot 的群组或频道列表
    allowed_chats: List[int] = []
    # 大部分请求所使用的代理: http://
    proxy: Optional[str] = None
    # telegram api id
    api_id: int = 1025907  # get it from https://core.telegram.org/api/obtaining_api_id
    # telegram api hash, get it from https://core.telegram.org/api/obtaining_api_hash
    api_hash: str = "452b0359b988148995f22ff0f4229750"
    # saucenao APIKEY，必填，否则无法使用 saucenao 搜图
    saucenao_api_key: str
    # exhentai cookies，选填，没有的情况下自动改用 e-hentai 搜图
    exhentai_cookies: Optional[str] = None
    # 用来绕过 nhentai cloudflare 拦截的 useragent
    nhentai_useragent: Optional[str] = None
    # 用来绕过 nhentai cloudflare 拦截的 cookie
    nhentai_cookies: Optional[str] = None

    @validator("token", "owner_id", "saucenao_api_key", pre=True)
    def check_required(cls, v: Any) -> Any:
        if not v:
            raise ValueError("token / owner_id / saucenao_api_key are required!")
        return v


config = Config(_env_file=".env", _env_file_encoding="utf-8")
