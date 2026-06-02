"""HTTP 缓存控制中间件

为 GET 请求添加 Cache-Control 响应头，支持基于路径的缓存策略配置。
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# 缓存策略配置：路径前缀 -> max-age (秒)
# 0 表示不缓存，-1 表示使用默认不设置头
CACHE_POLICIES: dict[str, int] = {
    # 预置技能市场 - 变化较少，可缓存较长时间
    "/api/v1/storage/skills": 300,  # 5 分钟
    # 用户技能配置 - 变化中等
    "/api/v1/storage/users": 60,  # 1 分钟
    # 智能体列表 - 变化中等
    "/api/v1/user-agents": 60,  # 1 分钟
    # 聊天历史 - 不缓存（可能随时有新消息）
    "/api/v1/chats": 0,
}


def get_cache_max_age(path: str) -> int | None:
    """根据路径获取缓存时间

    Args:
        path: 请求路径

    Returns:
        缓存时间（秒），None 表示不设置缓存头
    """
    for prefix, max_age in CACHE_POLICIES.items():
        if path.startswith(prefix):
            return max_age
    return None


class CacheControlMiddleware(BaseHTTPMiddleware):
    """HTTP 缓存控制中间件

    仅对 GET 请求添加 Cache-Control 头。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # 仅对 GET 请求设置缓存头
        if request.method != "GET":
            return response

        # 跳过已设置缓存头的响应
        if "Cache-Control" in response.headers:
            return response

        # 根据路径获取缓存策略
        max_age = get_cache_max_age(request.url.path)

        if max_age is not None:
            if max_age == 0:
                # 不缓存
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            else:
                # 设置缓存时间
                response.headers["Cache-Control"] = f"private, max-age={max_age}"

        return response
