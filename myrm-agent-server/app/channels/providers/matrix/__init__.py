"""Matrix channel provider with optional E2E encryption (E2EE).

Uses the mautrix Python SDK for Matrix Client-Server API and Olm/Megolm
crypto operations. Supports token-based and password-based authentication,
DM identification, proxy configuration, and encrypted attachment handling.
"""

from app.channels.providers.matrix.channel import MatrixChannel

__all__ = ["MatrixChannel"]
