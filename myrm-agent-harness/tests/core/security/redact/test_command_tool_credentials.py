"""A password or passphrase typed as an argument of ``docker login``, ``redis-cli``, ``openssl`` or ``curl --proxy-user``.

Like ``curl -u`` and ``sshpass -p``, these options carry the credential under a name that says nothing (``-p`` is a port
for ``docker run``, ``-a`` and ``--pass`` are the password of ``redis-cli`` whose port is ``-p``), so each rule is
anchored on the command name and stays inside one command. References (``$VAR``, ``env:``, ``file:``) and options that
only look alike stay readable.
"""

from __future__ import annotations

import json
import time

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_PASSWORD = "s3cretPw99"


def _masked(text: str) -> str:
    return redact_sensitive_text(text)


class TestCurlProxyUser:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"curl --proxy-user admin:{_PASSWORD} https://x", "curl --proxy-user admin:*** https://x"),
            (f"curl --proxy-user=admin:{_PASSWORD} https://x", "curl --proxy-user=admin:*** https://x"),
            (f"curl -U admin:{_PASSWORD} https://x", "curl -U admin:*** https://x"),
            (f"curl -Uadmin:{_PASSWORD} https://x", "curl -Uadmin:*** https://x"),
            (f"curl -sSU admin:{_PASSWORD} https://x", "curl -sSU admin:*** https://x"),
            ("curl -x http://p:8080 --proxy-user 'admin:p ass w0rd' https://x", "curl -x http://p:8080 --proxy-user 'admin:***' https://x"),
            (f"curl -u a:{_PASSWORD} -U b:{_PASSWORD} https://x", "curl -u a:*** -U b:*** https://x"),
        ],
    )  # fmt: skip
    def test_the_proxy_password_is_masked_and_the_user_is_kept(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    @pytest.mark.parametrize(
        "command",
        [
            "curl --proxy-user $PROXY_USER:$PROXY_PASS https://x",
            "curl --proxy-user admin https://x",
            "curl --proxy-user admin:*** https://x",
            "curl -x http://proxy:8080 https://x",
            "curl --proxy-header 'A: b' https://x",
            "curl -A Mozilla:5.0 https://x",
            "wget -U Mozilla:5.0 https://x",
        ],
    )  # fmt: skip
    def test_a_reference_a_missing_password_and_other_options_stay_readable(self, command: str) -> None:
        assert _masked(command) == command


class TestCurlSeveralCredentials:
    """One curl command carries a login, a proxy login and a cookie together; every one is masked."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"curl -u a:{_PASSWORD} -b 'sid={_PASSWORD}' https://x", "curl -u a:*** -b '***' https://x"),
            (f"curl -b 'sid={_PASSWORD}' -u a:{_PASSWORD} https://x", "curl -b '***' -u a:*** https://x"),
            (
                f"curl -x http://p:8080 -u a:{_PASSWORD} -H 'A: b' --proxy-user c:{_PASSWORD} https://x",
                "curl -x http://p:8080 -u a:*** -H 'A: b' --proxy-user c:*** https://x",
            ),
            (
                f"curl -u a:{_PASSWORD} \\\n  --proxy-user c:{_PASSWORD} \\\n  --cookie sid={_PASSWORD} https://x",
                "curl -u a:*** \\\n  --proxy-user c:*** \\\n  --cookie *** https://x",
            ),
        ],
    )  # fmt: skip
    def test_every_option_of_the_command_is_masked(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    def test_the_options_of_two_commands_are_masked_each(self) -> None:
        text = f"curl -u a:{_PASSWORD} https://x && curl -u b:{_PASSWORD} -b 'sid={_PASSWORD}' https://y"
        assert _masked(text) == "curl -u a:*** https://x && curl -u b:*** -b '***' https://y"

    def test_an_option_after_the_end_of_the_command_is_not_taken_for_curl(self) -> None:
        text = f"curl -u a:{_PASSWORD} https://x | sort -u k:{_PASSWORD}"
        assert _masked(text) == f"curl -u a:*** https://x | sort -u k:{_PASSWORD}"

    def test_the_masked_text_is_stable(self) -> None:
        once = _masked(f"curl -u a:{_PASSWORD} -b 'sid={_PASSWORD}' --proxy-user c:{_PASSWORD} https://x")
        assert _masked(once) == once


class TestDockerLogin:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"docker login -u me -p {_PASSWORD} registry.example.com", "docker login -u me -p *** registry.example.com"),
            (f"docker login -p {_PASSWORD} -u me", "docker login -p *** -u me"),
            (f"docker login registry.example.com -u me -p {_PASSWORD}", "docker login registry.example.com -u me -p ***"),
            (f"docker login -u me --password {_PASSWORD} reg.io", "docker login -u me --password *** reg.io"),
            (f"docker login -u me --password={_PASSWORD} reg.io", "docker login -u me --password=*** reg.io"),
            (f"docker login -u me -p{_PASSWORD} reg.io", "docker login -u me -p*** reg.io"),
            (f"docker login -u me -p '{_PASSWORD} x' reg.io", "docker login -u me -p '***' reg.io"),
            (f'docker login -u me -p "{_PASSWORD}" reg.io', 'docker login -u me -p "***" reg.io'),
            (f"docker  login -u me -p {_PASSWORD}", "docker  login -u me -p ***"),
            (f"/usr/local/bin/docker login -u me -p {_PASSWORD} reg.io", "/usr/local/bin/docker login -u me -p *** reg.io"),
            (f"echo ok && docker login -u me -p {_PASSWORD} reg.io", "echo ok && docker login -u me -p *** reg.io"),
            (f"docker login \\\n  -u me \\\n  -p {_PASSWORD} reg.io", "docker login \\\n  -u me \\\n  -p *** reg.io"),
        ],
    )  # fmt: skip
    def test_the_password_is_masked_and_the_rest_is_kept(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    @pytest.mark.parametrize(
        "command",
        [
            "docker run -p 8080:80 nginx",
            "docker run -d -p 5432:5432 -e POSTGRES_USER=app postgres",
            "docker login reg.io",
            "docker login -u me --password-stdin reg.io",
            "docker login --password-stdin < pw.txt",
            "docker login -u me -p $REGISTRY_PASSWORD reg.io",
            'docker login -u me -p "${REGISTRY_PASSWORD}" reg.io',
            "docker login -u me -p *** reg.io",
            "docker login reg.io && docker run -p 8080:80 nginx",
            "docker login reg.io; docker run -p 8080:80 nginx",
            "docker login reg.io\ndocker run -p 8080:80 nginx",
            "docker ps -p",
            "mydocker login -u me -p pw reg.io",
        ],
    )  # fmt: skip
    def test_a_port_a_reference_stdin_and_other_commands_stay_readable(self, command: str) -> None:
        assert _masked(command) == command

    def test_the_command_inside_a_json_string_is_masked(self) -> None:
        record = json.dumps({"command": f"docker login -u me -p {_PASSWORD} reg.io", "exit_code": 0})
        assert json.loads(_masked(record)) == {"command": "docker login -u me -p *** reg.io", "exit_code": 0}


class TestRedisCli:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"redis-cli -h cache -a {_PASSWORD} ping", "redis-cli -h cache -a *** ping"),
            (f"redis-cli -a {_PASSWORD}", "redis-cli -a ***"),
            (f"redis-cli -a{_PASSWORD} ping", "redis-cli -a*** ping"),
            (f"redis-cli --pass {_PASSWORD} ping", "redis-cli --pass *** ping"),
            (f"redis-cli --pass={_PASSWORD} ping", "redis-cli --pass=*** ping"),
            (f"redis-cli -a '{_PASSWORD} x' ping", "redis-cli -a '***' ping"),
            (f"redis-cli -p 6379 -a {_PASSWORD} -n 2 ping", "redis-cli -p 6379 -a *** -n 2 ping"),
            (f"redis-cli -u redis://cache:6379 -a {_PASSWORD} info", "redis-cli -u redis://cache:6379 -a *** info"),
            (f"redis-cli -h cache \\\n  -a {_PASSWORD} ping", "redis-cli -h cache \\\n  -a *** ping"),
        ],
    )  # fmt: skip
    def test_the_password_is_masked_and_the_rest_is_kept(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    @pytest.mark.parametrize(
        "command",
        [
            "redis-cli -p 6379 ping",
            "redis-cli -h cache -p 6379 -n 2 ping",
            "redis-cli --askpass",
            "redis-cli --user app --no-auth-warning ping",
            "redis-cli --pass-through ping",
            "redis-cli -a $REDISCLI_AUTH ping",
            "redis-cli -a *** ping",
            "redis-cli -a",
            "redis-cli ping | sort -a b",
            "myredis-cli -a pw ping",
        ],
    )  # fmt: skip
    def test_a_port_a_prompt_a_reference_and_other_commands_stay_readable(self, command: str) -> None:
        assert _masked(command) == command

    def test_the_command_inside_a_json_string_is_masked(self) -> None:
        record = json.dumps({"command": f"redis-cli -a {_PASSWORD} ping"})
        assert json.loads(_masked(record)) == {"command": "redis-cli -a *** ping"}


class TestOpensslPassphrase:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (f"openssl enc -aes-256-cbc -pass pass:{_PASSWORD} -in a -out b", "openssl enc -aes-256-cbc -pass pass:*** -in a -out b"),
            (f"openssl pkcs12 -export -passout pass:{_PASSWORD} -in a", "openssl pkcs12 -export -passout pass:*** -in a"),
            (f"openssl pkcs12 -in a.p12 -passin pass:{_PASSWORD}", "openssl pkcs12 -in a.p12 -passin pass:***"),
            (f"openssl pkcs12 -in a.p12 -password pass:{_PASSWORD}", "openssl pkcs12 -in a.p12 -password pass:***"),
            (f'openssl enc -pass "pass:{_PASSWORD}" -in a', 'openssl enc -pass "pass:***" -in a'),
            ("openssl enc -pass 'pass:my pass phrase' -in a", "openssl enc -pass 'pass:***' -in a"),
            (f"openssl enc -pass pass:{_PASSWORD} \\\n  -in a", "openssl enc -pass pass:*** \\\n  -in a"),
            (f"/usr/bin/openssl enc -pass pass:{_PASSWORD}", "/usr/bin/openssl enc -pass pass:***"),
        ],
    )  # fmt: skip
    def test_the_passphrase_is_masked_and_the_rest_is_kept(self, command: str, expected: str) -> None:
        assert _masked(command) == expected

    @pytest.mark.parametrize(
        "command",
        [
            "openssl enc -aes-256-cbc -pass env:ARCHIVE_KEY -in a",
            "openssl enc -pass file:/run/secrets/key -in a",
            "openssl enc -pass stdin -in a",
            "openssl enc -pass fd:3 -in a",
            "openssl enc -pass pass:$ARCHIVE_KEY -in a",
            "openssl req -new -passout pass: -out r.csr",
            "openssl enc -pass pass:*** -in a",
            "openssl rand -hex 16",
            "openssl s_client -connect example.com:443",
            "echo -pass pass:abc123",
            "myopenssl enc -pass pass:abc123",
        ],
    )  # fmt: skip
    def test_a_reference_another_source_and_other_commands_stay_readable(self, command: str) -> None:
        assert _masked(command) == command

    def test_the_command_inside_a_json_string_is_masked(self) -> None:
        record = json.dumps({"command": f'openssl enc -pass "pass:{_PASSWORD}" -in a'})
        assert json.loads(_masked(record)) == {"command": 'openssl enc -pass "pass:***" -in a'}


class TestPipelineBehaviour:
    @pytest.mark.parametrize(
        "command",
        [
            f"curl --proxy-user admin:{_PASSWORD} https://x",
            f"docker login -u me -p {_PASSWORD} reg.io",
            f"redis-cli -a {_PASSWORD} ping",
            f"openssl enc -pass pass:{_PASSWORD} -in a",
        ],
    )  # fmt: skip
    def test_masking_twice_changes_nothing(self, command: str) -> None:
        once = _masked(command)
        assert _PASSWORD not in once
        assert _masked(once) == once

    def test_each_command_of_one_record_is_masked(self) -> None:
        command = f"docker login -u me -p {_PASSWORD} reg.io && redis-cli -a {_PASSWORD} ping"
        assert _masked(command) == "docker login -u me -p *** reg.io && redis-cli -a *** ping"


class TestCostStaysLinear:
    """A long record that repeats the command name does a bounded amount of work per occurrence."""

    @pytest.mark.parametrize(
        "unit",
        ["docker login ", "docker login -p ", "redis-cli ", "redis-cli -a ", "openssl ", "openssl -pass ", "sshpass -e "],
    )  # fmt: skip
    def test_a_long_run_of_the_command_is_masked_in_proportional_time(self, unit: str) -> None:
        def seconds(repeats: int) -> float:
            text = unit * repeats
            start = time.process_time()
            redact_sensitive_text(text)
            return time.process_time() - start

        small = min(seconds(4_000) for _ in range(3))
        large = min(seconds(16_000) for _ in range(3))
        assert large < max(small * 12, 0.5)
