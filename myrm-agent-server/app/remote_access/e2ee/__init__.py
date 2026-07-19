"""Remote-access E2EE subpackage.

[INPUT]
- app.remote_access.e2ee.crypto (POS: NaCl box primitives)
- app.remote_access.e2ee.keystore (POS: daemon X25519 keypair persistence)
- app.remote_access.e2ee.session (POS: in-memory session registry)
- app.remote_access.e2ee.response (POS: encrypted JSON API responses)
- app.remote_access.e2ee.sse (POS: encrypted SSE stream frames)

[OUTPUT]
- Crypto, session, keystore, response, and SSE helpers for mobile remote E2EE.

[POS]
Mobile remote E2EE 子包聚合出口。对外统一导出加解密、会话、keystore 与响应/SSE 包装 API。
"""

from app.remote_access.e2ee.crypto import (
    E2EECryptoError,
    decrypt_utf8,
    encrypt_utf8,
    generate_keypair,
    public_key_b64,
    public_key_from_b64,
)
from app.remote_access.e2ee.keystore import DaemonKeypair, load_or_create_daemon_keypair
from app.remote_access.e2ee.response import e2ee_success_response, get_request_e2ee_session
from app.remote_access.e2ee.session import (
    E2EE_CONTENT_TYPE,
    E2EE_MAX_SESSIONS,
    E2EE_PAIR_CIPHERTEXT_HEADER,
    E2EE_PAIR_QUERY_PARAM,
    E2EE_SESSION_HEADER,
    E2EE_SESSION_TTL_SECONDS,
    E2EESession,
    E2EESessionStore,
    get_e2ee_session_store,
    parse_encrypted_body,
)
from app.remote_access.e2ee.sse import encrypt_sse_stream

__all__ = [
    "DaemonKeypair",
    "E2EECryptoError",
    "E2EE_CONTENT_TYPE",
    "E2EE_MAX_SESSIONS",
    "E2EE_PAIR_CIPHERTEXT_HEADER",
    "E2EE_PAIR_QUERY_PARAM",
    "E2EE_SESSION_HEADER",
    "E2EE_SESSION_TTL_SECONDS",
    "E2EESession",
    "E2EESessionStore",
    "decrypt_utf8",
    "e2ee_success_response",
    "encrypt_sse_stream",
    "encrypt_utf8",
    "generate_keypair",
    "get_e2ee_session_store",
    "get_request_e2ee_session",
    "load_or_create_daemon_keypair",
    "parse_encrypted_body",
    "public_key_b64",
    "public_key_from_b64",
]
