"""Host-class contract shared by the Feishu document mixins.

[INPUT]
- (none — typing contract only)

[OUTPUT]
- FeishuHost: the members FeishuClient provides to every document mixin.

[POS]
Declares once what a document mixin may call on its host; each mixin inherits it instead of restating it.
The methods exist for type checkers only, so they can never shadow the real ones FeishuClient defines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx


class FeishuHost:
    """Members the host ``FeishuClient`` supplies to the document mixins."""

    api_base: str
    _MEDIA_TIMEOUT: float

    if TYPE_CHECKING:

        async def ensure_token(self) -> str: ...
        def _get_http(self) -> httpx.AsyncClient: ...
        def _auth(self, token: str) -> dict[str, str]: ...
        def _safe_json(self, resp: httpx.Response, operation: str) -> dict[str, object]: ...
