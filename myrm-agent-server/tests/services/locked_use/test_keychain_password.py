"""Keychain unlock-password retrieval: decoding of ``security find-generic-password -g``.

[INPUT]
- app.services.locked_use.service.MacScreenUnlocker.get_password / _parse_keychain_password
  (POS: Keychain 解锁密码读取)
- macOS ``security`` CLI（live 用例，POS: 真实钥匙串往返）

[OUTPUT]
- 密码行解码（普通文本 / 十六进制 / 异常输入）与读取失败降级的回归断言
- 真实钥匙串往返：非 ASCII、引号、反斜杠、纯数字、首尾空白密码逐字节还原

[POS]
`security -w` 对非 ASCII 密码输出无标记的十六进制，会让 server 把十六进制串当密码键入
登录窗；读取改走 ``-g`` 的带标记输出。解析样例均取自真实 macOS 输出。
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from app.services.locked_use.service import MacScreenUnlocker, _parse_keychain_password


@pytest.mark.parametrize(
    ("security_stderr", "expected"),
    [
        ('password: "plain"\n', "plain"),
        # 看起来像十六进制的明文必须按文本处理，不得被误解码。
        ('password: "1234"\n', "1234"),
        ('password: "deadbeef"\n', "deadbeef"),
        ('password: "quote"inside"\n', 'quote"inside'),
        ('password: "trailing space "\n', "trailing space "),
        ("password: 0xE5AF86E7A081C3A9F09F9880 \n", "密码é😀"),
        ('password: 0x7461620968657265  "tab\\011here"\n', "tab\there"),
        ('password: 0x615C62  "a\\134b"\n', "a\\b"),
        ('password: ""\n', ""),
        # -g 的其余输出（keychain / attributes 在 stdout，stderr 仅此一行）混入时仍取密码行。
        ('keychain: "/x/login.keychain-db"\npassword: "plain"\n', "plain"),
    ],
)
def test_parse_decodes_text_and_hex_forms(security_stderr: str, expected: str) -> None:
    assert _parse_keychain_password(security_stderr) == expected


@pytest.mark.parametrize(
    "security_stderr",
    [
        "",
        "security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.\n",
        "password: <NULL>\n",
        "password: 0xABC\n",  # 奇数位十六进制
        "password: 0xFF\n",  # 非 UTF-8 字节
    ],
)
def test_parse_rejects_unusable_output(security_stderr: str) -> None:
    assert _parse_keychain_password(security_stderr) is None


class TestGetPassword:
    @patch("subprocess.run")
    def test_reads_via_marked_output_never_hex_encoded_w(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b'password: "my_password"\n')
        assert MacScreenUnlocker.get_password() == "my_password"
        argv = mock_run.call_args.args[0]
        assert "-g" in argv
        assert "-w" not in argv

    @patch("subprocess.run")
    def test_empty_password_counts_as_missing(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b'password: ""\n')
        assert MacScreenUnlocker.get_password() is None

    @pytest.mark.parametrize(
        "failure",
        [
            subprocess.CalledProcessError(44, ["security"]),
            OSError("security not found"),
            subprocess.TimeoutExpired(["security"], 1),
        ],
    )
    @patch("subprocess.run")
    def test_lookup_failures_degrade_to_none(self, mock_run: MagicMock, failure: Exception) -> None:
        mock_run.side_effect = failure
        assert MacScreenUnlocker.get_password() is None


@pytest.fixture
def throwaway_item(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Point the unlocker at a unique Keychain service so the real credential is never touched."""
    service = f"com.myrm.agent.test.{uuid.uuid4().hex}"
    monkeypatch.setattr(MacScreenUnlocker, "KEYCHAIN_SERVICE", service)
    try:
        yield service
    finally:
        subprocess.run(
            ["security", "delete-generic-password", "-s", service, "-a", MacScreenUnlocker.KEYCHAIN_ACCOUNT],
            capture_output=True,
            check=False,
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain")
@pytest.mark.parametrize(
    "password",
    ["plain", "1234", "deadbeef", 'quote"inside', "back\\slash", "密码é😀", " padded ", "tab\there"],
)
def test_live_keychain_round_trips_byte_exact(throwaway_item: str, password: str) -> None:
    """Real ``security`` output (no mock): what the shell stores is exactly what gets typed."""
    stored = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-s",
            throwaway_item,
            "-a",
            MacScreenUnlocker.KEYCHAIN_ACCOUNT,
            "-w",
            password,
            "-U",
        ],
        capture_output=True,
        check=False,
    )
    if stored.returncode != 0:
        pytest.skip("login keychain is not writable in this environment")
    assert MacScreenUnlocker.get_password() == password
