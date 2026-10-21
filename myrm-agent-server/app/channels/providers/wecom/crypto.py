"""WeCom (Enterprise WeChat) message encryption/decryption.

Implements WXBizMsgCrypt: AES-CBC-256 encryption with PKCS7 padding
and SHA1 signature verification for WeCom callback messages.

[INPUT]

[OUTPUT]
- WeComCrypto: encrypt/decrypt/verify for WeCom XML messages

[POS]
WeCom message encryption/decryption. Implements AES-CBC + PKCS7 padding + SHA1
signature verification for Webhook callback message security.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct

import defusedxml.ElementTree as ET
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


class WeComCrypto:
    """WeCom message encryption/decryption (WXBizMsgCrypt)."""

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str) -> None:
        self._token = token
        self._corp_id = corp_id
        self._key = base64.b64decode(encoding_aes_key + "=")
        self._iv = self._key[:16]

    def verify_signature(self, signature: str, timestamp: str, nonce: str, encrypt: str) -> bool:
        """Verify SHA1 signature of the encrypted message (constant-time) and prevent replay attacks."""
        import logging
        import time

        logger = logging.getLogger(__name__)
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 300:  # 5 minutes replay protection
                logger.warning("WeCom signature verification failed: timestamp expired (replay attack protection)")
                return False
        except ValueError:
            return False

        items = sorted([self._token, timestamp, nonce, encrypt])
        sha1 = hashlib.sha1("".join(items).encode()).hexdigest()
        return hmac.compare_digest(sha1, signature)

    def decrypt(self, encrypted: str) -> str:
        """Decrypt an AES-CBC-256 encrypted message with PKCS7 padding."""
        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv))
        decryptor = cipher.decryptor()
        plain = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()

        unpadder = PKCS7(128).unpadder()
        plain = unpadder.update(plain) + unpadder.finalize()

        content_len = struct.unpack("!I", plain[16:20])[0]
        content = plain[20 : 20 + content_len].decode("utf-8")
        from_corp_id = plain[20 + content_len :].decode("utf-8")

        if from_corp_id != self._corp_id:
            raise ValueError(f"Corp ID mismatch: expected {self._corp_id}, got {from_corp_id}")

        return content

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext message for WeCom."""
        random_bytes = os.urandom(16)
        content_bytes = plaintext.encode("utf-8")
        corp_bytes = self._corp_id.encode("utf-8")
        body = random_bytes + struct.pack("!I", len(content_bytes)) + content_bytes + corp_bytes

        padder = PKCS7(128).padder()
        padded = padder.update(body) + padder.finalize()

        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()

        return base64.b64encode(encrypted).decode("utf-8")

    @staticmethod
    def extract_encrypted_from_xml(xml_text: str) -> str:
        """Extract the Encrypt field from WeCom callback XML."""
        root = ET.fromstring(xml_text)
        encrypt_node = root.find("Encrypt")
        if encrypt_node is None or encrypt_node.text is None:
            raise ValueError("Missing <Encrypt> in XML")
        return encrypt_node.text
