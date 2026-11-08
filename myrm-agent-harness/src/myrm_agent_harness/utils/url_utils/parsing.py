"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- url_dedup_key: URL 去重键，把同一页面的不同拼写折叠成同一个键，只用于比较；可选把锚点计入键
- readable_url: 供展示与引用的 URL，保持供应商原样，只还原非 ASCII 字符的百分号转义
- extract_domain
- is_valid_image_url
- is_image_url
- is_file_url

[POS]
URL 去重键、展示 URL、域名提取与图片/文件 URL 判断；不做安全校验。
"""

from __future__ import annotations

import re
from urllib.parse import unquote, unquote_to_bytes, urlparse, urlunparse

# 一段连续的非 ASCII 百分号转义：UTF-8 多字节序列的每个字节都不小于 0x80。
_NON_ASCII_ESCAPE_RUN = re.compile(r"(?:%[89A-Fa-f][0-9A-Fa-f])+")


# ============================================================================
# URL 去重键与展示
# ============================================================================


def url_dedup_key(url: str, *, keep_fragment: bool = False) -> str:
    """URL 去重键: 解码+小写+去www+去尾斜杠（站点根路径统一为 /）+去fragment。

    同一页面的不同拼写（大小写、www、尾斜杠、百分号编码、锚点）得到同一个键。
    需要把同一页面的不同锚点当作不同来源时传 keep_fragment=True：锚点区分大小写，只解码，计入键。
    键只用于比较，不能展示或访问：路径已被小写，区分大小写的路径（B 站 BV 号、YouTube 短 id）
    在键里无法还原，展示请用 readable_url。

    Args:
        url: 要计算键的URL
        keep_fragment: 为 True 时锚点计入键，默认丢弃

    Returns:
        去重键。URL 无法解析时返回原 URL，空串返回空串。

    示例：
        url_dedup_key("https://www.Example.com/A%20b/#top")  # "https://example.com/a b"
        url_dedup_key("https://example.com")  # "https://example.com/"
    """
    try:
        parts = urlparse(url)
        scheme = (parts.scheme or "").lower()
        netloc = (parts.netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # 解码并小写化 path，确保 /Wiki/ 与 /wiki/、%E4%B8%AD 与 中 被识别为同一页面
        path = unquote(parts.path or "").lower()
        if len(path) > 1:
            path = path.rstrip("/")
        # 有主机的 URL：无路径与 "/" 是同一资源（RFC 3986 §6.2.3）；"//"、"///" 这类连续斜杠是本项目为比较做的折叠，
        # 规范并不认为它们等价。它们都当作站点根页面，统一写成 "/"
        if netloc and not path:
            path = "/"

        # query 的 value 通常区分大小写，只解码，不小写化
        query = unquote(parts.query or "")

        fragment = unquote(parts.fragment) if keep_fragment else ""

        return urlunparse((scheme, netloc, path, "", query, fragment))
    except Exception:
        return url


def readable_url(url: str) -> str:
    """供展示与引用的 URL: 保持供应商给出的原样，只把非 ASCII 字符的百分号转义还原成字符。

    大小写、www、尾斜杠、query、fragment 都不动，区分大小写的路径（B 站 BV 号、YouTube 短 id）
    因此仍然可访问。中文等字符还原后更短，模型也更容易读懂。
    ASCII 转义（%20、%2F、%26 ...）承载 URL 的结构，还原会改变含义（例如跳转包装链接的 query 会被拆开），所以不动。
    只还原整段合法 UTF-8 且可打印的转义：截断的字节、零宽字符、不间断空格、双向控制符保持编码。

    Args:
        url: 供应商返回的URL

    Returns:
        展示用 URL；没有可还原的转义时与输入相同。

    示例：
        readable_url("https://zh.wikipedia.org/wiki/%E8%8B%B1%E9%9B%84#%E5%8E%86%E5%8F%B2")
        # "https://zh.wikipedia.org/wiki/英雄#历史"
    """
    return _NON_ASCII_ESCAPE_RUN.sub(_decode_readable_run, url)


def _decode_readable_run(match: re.Match[str]) -> str:
    """整段转义解码成可打印文本；不是合法 UTF-8 或含不可打印字符时保持原样。"""
    escaped = match.group()
    try:
        decoded = unquote_to_bytes(escaped).decode("utf-8")
    except UnicodeDecodeError:
        return escaped
    return decoded if decoded.isprintable() else escaped


# ============================================================================
# URL 解析和提取
# ============================================================================


def extract_domain(url: str) -> str:
    """提取域名(去www)。"""
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


# ============================================================================
# URL 类型判断
# ============================================================================


def is_valid_image_url(url: str) -> bool:
    """判断URL是否是公网地址

    Args:
        url: 图片URL

    Returns:
        是否可直接访问
    """
    parsed = urlparse(url)

    # HTTP协议通常不能直接访问
    if parsed.scheme == "http":
        return False

    # 本地服务地址不能直接访问
    local_hosts = ["localhost", "127.0.0.1", "0.0.0.0"]  # noqa: S104  # hostname list, not a bind
    if parsed.hostname in local_hosts:
        return False

    # 内网IP地址不能直接访问
    if parsed.hostname and (
        parsed.hostname.startswith("192.168.")
        or parsed.hostname.startswith("10.")
        or parsed.hostname.startswith("172.")
    ):
        return False

    # HTTPS且非本地地址可以直接访问
    return parsed.scheme == "https"


def is_image_url(url: str) -> bool:
    """判断URL是否为图片链接

    Args:
        url: 要判断的URL

    Returns:
        是否为图片链接
    """
    image_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".svg",
        ".webp",
        ".ico",
    )

    # 提取URL路径，去除查询参数
    url_lower = url.lower()
    path = url_lower.split("?")[0]

    # 检查是否以图片扩展名结尾
    return any(path.endswith(ext) for ext in image_extensions)


def is_file_url(url: str) -> bool:
    """判断URL是否为文件资源链接（只要包含扩展名即视为文件）

    Args:
        url: 要判断的URL

    Returns:
        是否为文件资源链接
    """
    # 提取URL路径部分（去除查询参数和锚点）
    path = url.lower().split("?")[0].split("#")[0]
    # 检查路径中是否包含点号后跟字母（简单扩展名判断）
    return "." in path and path.rsplit(".", 1)[1].isalpha()
