"""Tests for the environment and git-credential injection a PersistentSession adds to commands."""

from __future__ import annotations

import base64
import os
import shlex
import shutil
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
)
from myrm_agent_harness.toolkits.code_execution.session.models import SessionExecutionResult
from tests.toolkits.code_execution._session_helpers import make_config


class TestSmartEnvInjection:
    @pytest.mark.asyncio
    async def test_global_defense_env_vars(self) -> None:
        """Test that global defense environment variables (CI, NEXT_TELEMETRY_DISABLED) are set."""
        config = make_config()
        session = LocalPersistentSession(config)
        await session.start()
        try:
            import os

            script_path = os.path.join(
                os.path.dirname(__file__),
                "../../../src/myrm_agent_harness/agent/meta_tools/bash/scripts/resilience_init.sh",
            )
            # The product puts this script in front of every command, so a command here sources it first.
            result = await session.execute(f"source {script_path}\nenv | grep -E '^(CI|NEXT_TELEMETRY_DISABLED)='")
            assert "CI=1" in result.stdout
            assert "NEXT_TELEMETRY_DISABLED=1" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        shutil.which("npm") is None,
        reason="npm is not installed in the current environment",
    )
    async def test_smart_local_env_injection_for_build(self) -> None:
        """Test that SKIP_ENV_VALIDATION is injected for build commands but not for normal commands."""
        config = make_config()
        session = LocalPersistentSession(config)
        await session.start()
        try:
            import os

            script_path = os.path.join(
                os.path.dirname(__file__),
                "../../../src/myrm_agent_harness/agent/meta_tools/bash/scripts/resilience_init.sh",
            )

            async def run_with_script(command: str) -> SessionExecutionResult:
                # The product puts this script in front of every command, so a command here sources it first.
                return await session.execute(f"source {script_path}\n{command}")

            # Create a real package.json to test actual npm behavior
            await session.execute(
                'echo \'{"scripts": {"build": "env | grep -E \\"SKIP_ENV_VALIDATION|IGNORE_ENV_VALIDATION\\" || true", "test": "env | grep -E \\"SKIP_ENV_VALIDATION|IGNORE_ENV_VALIDATION\\" || true", "dev": "env | grep -E \\"SKIP_ENV_VALIDATION|IGNORE_ENV_VALIDATION\\" || true"}}\' > package.json'
            )

            # 1. Test npm run build (should inject)
            result = await run_with_script("npm run build")
            assert "SKIP_ENV_VALIDATION=1" in result.stdout
            assert "IGNORE_ENV_VALIDATION=1" in result.stdout

            # 2. Test npm test (should NOT inject)
            result2 = await run_with_script("npm test")
            assert "SKIP_ENV_VALIDATION=1" not in result2.stdout
            assert "IGNORE_ENV_VALIDATION=1" not in result2.stdout

            # 3. Test npm run dev (should inject)
            result3 = await run_with_script("npm run dev")
            assert "SKIP_ENV_VALIDATION=1" in result3.stdout

        finally:
            await session.execute("rm -f package.json")
            await session.close()


class TestResilienceGitCredentialInjection:
    """GitHub credential/identity injection guards in resilience_init.sh (git clone/push/commit).

    Verifies: HTTPS clone and push get an env-ref credential helper (token never inlined),
    SSH and third-party remotes passthrough, and commits resolve/inject identity only when
    the sandbox has none.
    """

    _RESILIENCE = os.path.join(
        os.path.dirname(__file__),
        "../../../src/myrm_agent_harness/agent/meta_tools/bash/scripts/resilience_init.sh",
    )

    _FAKE_GIT = """#!/bin/bash
echo "$@" >> "${FAKE_GIT_LOG}"
case "$1" in
  rev-parse)
    if [ "$2" = "--is-inside-work-tree" ]; then
      [ "$FAKE_GIT_IS_REPO" = "1" ] && exit 0 || exit 128
    fi
    exit 0;;
  config)
    case "$2" in
      --get)
        case "$3" in
          credential.helper) [ -n "$FAKE_GIT_CRED_HELPER" ] && { echo "$FAKE_GIT_CRED_HELPER"; exit 0; } || exit 1;;
          user.name) [ -n "$FAKE_GIT_NAME" ] && { echo "$FAKE_GIT_NAME"; exit 0; } || exit 1;;
          user.email) [ -n "$FAKE_GIT_EMAIL" ] && { echo "$FAKE_GIT_EMAIL"; exit 0; } || exit 1;;
          *) exit 1;;
        esac;;
      *) exit 0;;
    esac;;
  remote) [ -n "$FAKE_GIT_REMOTE" ] || exit 2; echo "$FAKE_GIT_REMOTE"; exit 0;;
  symbolic-ref) echo "feat/test"; exit 0;;
esac
exit 0
"""

    _FAKE_CURL = """#!/bin/bash
if [[ "$*" == *"api.github.com/user"* ]]; then
  echo '{"login":"octocat","id":1}'
fi
exit 0
"""

    @pytest.fixture(autouse=True)
    def _fake_dir(self, tmp_path: Path) -> None:
        # One directory per test: the tests of this class run side by side under xdist, and a path they
        # share is wiped by whichever starts next.
        self._dir = shlex.quote(str(tmp_path / "resilience_fake"))

    def _env(
        self,
        *,
        remote: str,
        token: str,
        cred_helper: str = "",
        name: str = "",
        email: str = "",
        is_repo: str = "1",
    ) -> str:
        return (
            f"FAKE_GIT_LOG={self._dir}/git.log "
            f"FAKE_GIT_IS_REPO={is_repo} FAKE_GIT_NAME={name} FAKE_GIT_EMAIL={email} "
            f"FAKE_GIT_CRED_HELPER={cred_helper} FAKE_GIT_REMOTE={remote} GITHUB_TOKEN={token}"
        )

    async def _run(self, env: str, cmd: str, pre_cache: str = "") -> str:
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            await session.execute(f"mkdir -p {self._dir}/home {self._dir}/tmp")
            if pre_cache:
                await session.execute(f"printf '%s' '{pre_cache}' > {self._dir}/tmp/myrm_gh_identity")
            for name, body in (("git", self._FAKE_GIT), ("curl", self._FAKE_CURL)):
                b64 = base64.b64encode(body.encode()).decode()
                await session.execute(f"echo {b64} | base64 -d > {self._dir}/{name} && chmod +x {self._dir}/{name}")
            # Isolate HOME so a host-level ~/.git-credentials (e.g. gh auth) cannot flip
            # _git_has_existing_credentials and skip helper injection. The identity cache lives under TMPDIR.
            # The product puts the resilience script in front of every command, so the command carries it too.
            await session.execute(
                f"export PATH={self._dir}:$PATH HOME={self._dir}/home TMPDIR={self._dir}/tmp {env}\n"
                f"source {self._RESILIENCE}\n{cmd}"
            )
            result = await session.execute(f"cat {self._dir}/git.log 2>/dev/null || true")
            return result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_push_https_injects_host_scoped_helper(self) -> None:
        """HTTPS GitHub push without existing credentials gets an env-ref helper gated on github.com hosts."""
        log = await self._run(
            self._env(remote="https://github.com/owner/repo.git", token="ghp_testtoken"),
            "git push origin main",
        )
        assert 'host=*) host="${line#host=}"' in log
        assert '"github.com"' in log
        assert 'password="${GITHUB_TOKEN}"' in log
        assert "password=ghp_testtoken" not in log

    @pytest.mark.asyncio
    async def test_push_ssh_passthrough(self) -> None:
        """SSH remote never receives a credential helper injection."""
        log = await self._run(
            self._env(remote="git@github.com:owner/repo.git", token="ghp_testtoken"),
            "git push origin main",
        )
        assert "-c credential.helper=" not in log
        assert "origin main" in log

    @pytest.mark.asyncio
    async def test_push_existing_helper_passthrough(self) -> None:
        """Existing credential.helper config suppresses injection."""
        log = await self._run(
            self._env(
                remote="https://github.com/owner/repo.git",
                token="ghp_testtoken",
                cred_helper="osxkeychain",
            ),
            "git push origin main",
        )
        assert "-c credential.helper=" not in log

    @pytest.mark.asyncio
    async def test_push_https_non_github_remote_passthrough(self) -> None:
        """HTTPS push to a third-party git host never gets the GitHub token."""
        log = await self._run(
            self._env(
                remote="https://gitlab.example.com/owner/repo.git",
                token="ghp_testtoken",
            ),
            "git push origin main",
        )
        assert "-c credential.helper=" not in log
        assert "origin main" in log

    @pytest.mark.asyncio
    async def test_push_www_github_host_scope(self) -> None:
        """www.github.com HTTPS push gets the host-scoped helper."""
        log = await self._run(
            self._env(remote="https://www.github.com/owner/repo.git", token="ghp_testtoken"),
            "git push origin main",
        )
        assert 'host=*) host="${line#host=}"' in log
        assert '"www.github.com"' in log
        assert "password=ghp_testtoken" not in log

    @pytest.mark.asyncio
    async def test_push_no_token_passthrough(self) -> None:
        """No GITHUB_TOKEN → no credential helper injection."""
        log = await self._run(
            self._env(remote="https://github.com/owner/repo.git", token=""),
            "git push origin main",
        )
        assert "-c credential.helper=" not in log
        assert "origin main" in log

    @pytest.mark.asyncio
    async def test_push_without_a_configured_remote_still_runs_under_errexit(self) -> None:
        """A failed remote lookup must not end a script running under ``set -e`` before git is called."""
        log = await self._run(
            self._env(remote="", token="ghp_testtoken"),
            "set -e\ngit push https://github.com/owner/repo.git main",
        )
        assert "push https://github.com/owner/repo.git main" in log

    @pytest.mark.asyncio
    async def test_clone_https_injects_host_scoped_helper(self) -> None:
        """An HTTPS GitHub clone gets the same env-ref helper as a push, so a private repository clones."""
        log = await self._run(
            self._env(remote="", token="ghp_testtoken"),
            "git clone https://github.com/owner/repo.git",
        )
        assert "-c credential.helper=" in log
        assert 'host=*) host="${line#host=}"' in log
        assert 'password="${GITHUB_TOKEN}"' in log
        assert "password=ghp_testtoken" not in log
        assert "clone https://github.com/owner/repo.git" in log

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [
            "https://gitlab.example.com/owner/repo.git",
            "git@github.com:owner/repo.git",
            "https://user:secret@github.com/owner/repo.git",
        ],
        ids=["third-party-host", "ssh", "credentials-in-url"],
    )
    async def test_clone_of_a_url_that_is_not_plain_https_github_passthrough(self, url: str) -> None:
        """Only an HTTPS GitHub URL without credentials of its own may be handed the GitHub token."""
        log = await self._run(self._env(remote="", token="ghp_testtoken"), f"git clone {url}")
        assert "-c credential.helper=" not in log
        assert f"clone {url}" in log

    @pytest.mark.asyncio
    async def test_commit_injects_resolved_identity(self) -> None:
        """Commit with no sandbox identity resolves GitHub login and injects user.name/email."""
        log = await self._run(
            self._env(remote="https://github.com/owner/repo.git", token="ghp_testtoken"),
            "git commit -m x",
        )
        assert "-c user.name=octocat" in log
        assert "user.email=octocat@users.noreply.github.com" in log

    @pytest.mark.asyncio
    async def test_commit_passthrough_with_identity(self) -> None:
        """Commit with configured identity passes through without injection."""
        log = await self._run(
            self._env(
                remote="https://github.com/owner/repo.git",
                token="ghp_testtoken",
                name="Jane",
                email="jane@example.com",
            ),
            "git commit -m x",
        )
        assert "user.name=" not in log
        assert "-m x" in log

    @pytest.mark.asyncio
    async def test_commit_non_repo_passthrough(self) -> None:
        """Commit outside a work tree passes through without identity resolution."""
        log = await self._run(
            self._env(
                remote="https://github.com/owner/repo.git",
                token="ghp_testtoken",
                is_repo="0",
            ),
            "git commit -m x",
        )
        assert "user.name=" not in log
        assert "-m x" in log

    @pytest.mark.asyncio
    async def test_commit_uses_cached_identity(self) -> None:
        """Commit identity resolution reuses the TMPDIR cache instead of calling the GitHub API."""
        log = await self._run(
            self._env(remote="https://github.com/owner/repo.git", token="ghp_testtoken"),
            "git commit -m x",
            pre_cache="cacheduser|cacheduser@users.noreply.github.com",
        )
        assert "-c user.name=cacheduser" in log
        assert "user.email=cacheduser@users.noreply.github.com" in log
