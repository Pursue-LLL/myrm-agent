"""URL 规范化、域名提取与图片/文件 URL 判断。

[POS]
url_utils 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from urllib.parse import unquote, urlparse, urlunparse

logger = logging.getLogger(__name__)


# ============================================================================
# URL 标准化和清理
# ============================================================================


def normalize_url(url: str) -> tuple[str, str]:
    """URL标准化: 解码+小写+去www+去尾斜杠，返回带/不带fragment的两个版本。

    标准化步骤：
    1. URL解码：将 %XX 编码转换为实际字符（如中文），确保嵌入模型能识别语义相似度
    2. 小写化：scheme、netloc和path全部转小写（确保大小写不同的URL能被识别为相同）
    3. 去除www前缀
    4. 去除路径尾部斜杠
    5. 保留query参数
    6. 返回两个版本：不带fragment（用于去重）和带fragment（用于语义分析）

    Args:
        url: 要标准化的URL

    Returns:
        (不带fragment的URL, 带fragment的URL)
        - 第一个：用于去重，同一页面的不同锚点会被识别为相同
        - 第二个：用于语义分析和显示，保留完整的定位信息

    使用场景：
        - 去重：使用返回的第一个值（不带fragment）作为去重key
        - 语义分析/显示：使用返回的第二个值（带fragment），存入metadata

    示例：
        # 基本用法
        url_dedup, url_semantic = normalize_url("https://docs.langchain.com/agents#system-prompt")
        # url_dedup: "https://docs.langchain.com/agents"
        # url_semantic: "https://docs.langchain.com/agents#system-prompt"

        # 中文URL解码
        url_dedup, url_semantic = normalize_url("https://zh.wikipedia.org/wiki/%E8%8B%B1%E9%9B%84%E8%81%94%E7%9B%9F#%E5%8E%86%E5%8F%B2")
        # url_dedup: "https://zh.wikipedia.org/wiki/英雄联盟"
        # url_semantic: "https://zh.wikipedia.org/wiki/英雄联盟#历史"
    """
    try:
        parts = urlparse(url)
        scheme = (parts.scheme or "").lower()
        netloc = (parts.netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # URL解码并小写化：将 %XX 编码转换为实际字符
        # 这对于中文URL至关重要，确保嵌入模型能正确识别语义
        # 同时小写化path，确保 /Wiki/ 和 /wiki/ 被识别为相同
        path = unquote(parts.path or "").lower()
        if len(path) > 1:
            path = path.rstrip("/")

        # 同样解码query参数（但query的value通常需要保持大小写，所以不小写化）
        query = unquote(parts.query or "")

        # 构建不带fragment的URL（用于去重）
        url_without_fragment = urlunparse((scheme, netloc, path, "", query, ""))

        # 构建带fragment的URL（用于语义分析和显示）
        fragment = unquote(parts.fragment or "") if parts.fragment else ""
        url_with_fragment = urlunparse((scheme, netloc, path, "", query, fragment))

        return url_without_fragment, url_with_fragment
    except Exception:
        return url, url


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


# ============================================================================
# SSRF 防护
# ============================================================================
