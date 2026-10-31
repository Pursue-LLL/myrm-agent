"""Channel connection probes: the credential checks behind the channel settings page.

[INPUT]
- connection_probes.bot_platforms::router (POS: probes for the hosted messaging platforms)
- connection_probes.error_text::safe_err_msg (POS: credential-safe error text)

[OUTPUT]
- router: ``POST /{platform}/test`` for Feishu, DingTalk, Slack, Discord, WeCom, Teams, Matrix, Telegram, Google Chat, QQ
- safe_err_msg: the error text every probe answers with

[POS]
Package facade; ``api/channels/test_connections.py`` mounts the router next to the probes it keeps itself.
"""

from .bot_platforms import router
from .error_text import safe_err_msg

__all__ = ["router", "safe_err_msg"]
