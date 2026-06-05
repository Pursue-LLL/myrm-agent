"""Shared helpers for Adversarial Verifier frontend E2E tests."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import httpx
from patchright.async_api import Page

from tests.support.test_secrets import apply_test_secrets_to_environ, resolve_test_env

apply_test_secrets_to_environ()

BACKEND_BASE = resolve_test_env("BACKEND_URL", "http://localhost:8080").rstrip("/")
FRONTEND_BASE = resolve_test_env("FRONTEND_URL", "http://localhost:3000").rstrip("/")


def require_env(name: str) -> str:
    value = resolve_test_env(name)
    if not value:
        raise RuntimeError(f"{name} must be set in .env.test")
    return value


def split_model(model: str) -> tuple[str, str]:
    if "/" not in model:
        raise RuntimeError(f"Invalid model format (expected provider/model): {model}")
    provider_id, model_name = model.split("/", 1)
    return provider_id, model_name


BASIC_MODEL = require_env("BASIC_MODEL")
LITE_MODEL = require_env("LITE_MODEL")
BASIC_PROVIDER, BASIC_MODEL_NAME = split_model(BASIC_MODEL)
LITE_PROVIDER, LITE_MODEL_NAME = split_model(LITE_MODEL)
BASIC_API_KEY = require_env("BASIC_API_KEY")
BASIC_BASE_URL = resolve_test_env("BASIC_BASE_URL")
LITE_API_KEY = require_env("LITE_API_KEY")
LITE_BASE_URL = resolve_test_env("LITE_BASE_URL")

_PROVIDER_DISPLAY: dict[str, str] = {
    "xiaomi_mimo": "Xiaomi MiMo",
    "minimax": "MiniMax",
}


def _build_api_key(api_key: str) -> dict[str, object]:
    return {
        "id": f"key_{uuid.uuid4().hex[:10]}",
        "key": api_key,
        "remark": "E2E default key",
        "isActive": True,
    }


def _patch_provider(
    providers: list[dict[str, object]],
    *,
    provider_id: str,
    api_key: str,
    api_url: str,
    model_name: str,
) -> None:
    for provider in providers:
        if provider.get("id") != provider_id:
            continue
        provider["isEnabled"] = True
        provider["apiUrl"] = api_url or provider.get("apiUrl", "")
        provider["apiKeys"] = [_build_api_key(api_key)]
        enabled = set(provider.get("enabledModels") or [])
        available = set(provider.get("availableModels") or [])
        enabled.add(model_name)
        available.add(model_name)
        provider["enabledModels"] = sorted(enabled)
        provider["availableModels"] = sorted(available)
        return
    raise RuntimeError(f"Provider {provider_id} not found in config")


SSE_CAPTURE_SCRIPT = """
() => {
  if (window.__e2eSseCaptureInstalled) return;
  window.__e2eSseCaptureInstalled = true;
  window.__e2eSseEvents = [];
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await origFetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    if (!url.includes('agent-stream')) {
      return response;
    }
    const clone = response.clone();
    void (async () => {
      const reader = clone.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            window.__e2eSseEvents.push(JSON.parse(line.slice(6)));
          } catch {
            /* ignore malformed SSE chunks */
          }
        }
      }
    })();
    return response;
  };
}
"""


def parse_sse_payload(raw: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            payload = json.loads(line[6:])
            if isinstance(payload, dict):
                events.append(payload)
        except json.JSONDecodeError:
            continue
    return events


class AgentStreamCapture:
    """Collect agent-stream SSE bodies from Playwright network responses."""

    def __init__(self) -> None:
        self._chunks: list[str] = []

    async def handle_response(self, response) -> None:
        if "agent-stream" not in response.url or response.request.method != "POST":
            return
        try:
            await asyncio.wait_for(response.finished(), timeout=180.0)
            body = await response.body()
            self._chunks.append(body.decode("utf-8", errors="replace"))
        except Exception:
            return

    def events(self) -> list[dict[str, object]]:
        parsed: list[dict[str, object]] = []
        for chunk in self._chunks:
            parsed.extend(parse_sse_payload(chunk))
        return parsed

    def clear(self) -> None:
        self._chunks.clear()

    def attach(self, page: Page) -> None:
        page.on("response", self.handle_response)


async def install_sse_capture(page: Page) -> None:
    """Install in-page fetch hook after the page is loaded (avoids init-script navigation issues)."""
    await page.evaluate(SSE_CAPTURE_SCRIPT)


async def get_captured_sse_events(page: Page) -> list[dict[str, object]]:
    raw = await page.evaluate("() => window.__e2eSseEvents || []")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def is_verifier_subagent_event(event: dict[str, object]) -> bool:
    if event.get("type") != "subagent_start":
        return False
    data = event.get("data")
    if not isinstance(data, dict):
        return False
    description = str(data.get("description", "")).lower()
    agent_type = str(data.get("agent_type", "")).lower()
    markers = (
        "adversarial sandbox verifier",
        "adversarial verifier",
        "独立审查",
        "verifier",
    )
    return any(marker in description or marker in agent_type for marker in markers)


def count_verifier_subagent_events(events: list[dict[str, object]]) -> int:
    return sum(1 for event in events if is_verifier_subagent_event(event))


async def _goto_with_retry(
    page: Page,
    url: str,
    *,
    wait_until: str = "domcontentloaded",
    attempts: int = 3,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await page.goto(url, timeout=120000, wait_until=wait_until)
            return
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            await page.wait_for_timeout(1500 * attempt)
    raise RuntimeError(f"Failed to open {url} after {attempts} attempts: {last_error}")


async def verify_providers_ready_in_ui(page: Page) -> None:
    """Open model settings and confirm env-configured providers are visible."""
    await _goto_with_retry(page, f"{FRONTEND_BASE}/settings/models")
    await page.wait_for_load_state("domcontentloaded", timeout=60000)
    basic_display = _PROVIDER_DISPLAY.get(BASIC_PROVIDER, BASIC_PROVIDER)
    await page.get_by_role("button", name=basic_display, exact=True).wait_for(state="visible", timeout=30000)
    await page.get_by_role("button", name=basic_display, exact=True).click()
    await page.wait_for_timeout(800)
    await page.get_by_text(BASIC_MODEL_NAME, exact=False).first.wait_for(state="visible", timeout=15000)


async def sync_providers_from_env() -> None:
    """Ensure backend provider config matches .env (used before UI verification)."""
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
        current = await client.get("/api/v1/config/providers")
        current.raise_for_status()
        body = current.json()
        value = body["value"]
        providers = value["providers"]
        version = body.get("version")

        _patch_provider(
            providers,
            provider_id=BASIC_PROVIDER,
            api_key=BASIC_API_KEY,
            api_url=BASIC_BASE_URL,
            model_name=BASIC_MODEL_NAME,
        )
        if LITE_PROVIDER != BASIC_PROVIDER or LITE_API_KEY != BASIC_API_KEY:
            _patch_provider(
                providers,
                provider_id=LITE_PROVIDER,
                api_key=LITE_API_KEY,
                api_url=LITE_BASE_URL,
                model_name=LITE_MODEL_NAME,
            )

        value["defaultModelConfig"] = {"baseModel": {"primary": {"providerId": BASIC_PROVIDER, "model": BASIC_MODEL_NAME}}}

        payload = {
            "changes": [
                {
                    "key": "providers",
                    "value": value,
                    "expectedVersion": version,
                    "timestamp": int(time.time() * 1000),
                }
            ],
            "deviceId": "verifier-e2e",
        }
        sync_resp = await client.post("/api/v1/config/sync", json=payload)
        sync_resp.raise_for_status()


async def _prepare_chat_session(page: Page, agent_id: str) -> None:
    await _goto_with_retry(page, f"{FRONTEND_BASE}/")
    await page.evaluate(
        """
        () => {
          localStorage.setItem('actionMode', 'agent');
          const security = JSON.parse(localStorage.getItem('securityConfig') || '{}');
          security.yoloModeEnabled = true;
          localStorage.setItem('securityConfig', JSON.stringify(security));
        }
        """
    )
    async with page.expect_response(
        lambda response: f"/api/v1/user-agents/{agent_id}" in response.url and response.request.method == "GET",
        timeout=60000,
    ) as agent_response_info:
        await _goto_with_retry(
            page,
            f"{FRONTEND_BASE}/?agent_id={agent_id}",
        )
    agent_response = await agent_response_info.value
    if agent_response.status != 200:
        raise RuntimeError(f"Failed to load agent profile {agent_id}: HTTP {agent_response.status}")
    await page.wait_for_timeout(1500)


async def bind_agent_to_chat(page: Page, agent_id: str) -> None:
    """Open home chat bound to the given agent profile."""
    await _prepare_chat_session(page, agent_id)


async def enable_adversarial_verifier_on_default_agent(page: Page) -> str:
    """Open home chat bound to a verifier-enabled agent."""
    agent_id = await ensure_verifier_agent_exists()
    await bind_agent_to_chat(page, agent_id)
    return agent_id


async def ensure_verifier_agent_exists() -> str:
    agent_name = "E2E Adversarial Verifier Agent"
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
        listing = await client.get("/api/v1/user-agents", params={"page": 1, "page_size": 100})
        listing.raise_for_status()
        payload = listing.json()
        agents = payload.get("data", payload if isinstance(payload, list) else [])
        if isinstance(agents, dict) and "items" in agents:
            agents = agents["items"]
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = str(agent["id"])
                await client.put(
                    f"/api/v1/user-agents/{agent_id}",
                    json={"engine_params": {"adversarial_verification": True}},
                )
                return agent_id

        create_resp = await client.post(
            "/api/v1/user-agents",
            json={
                "name": agent_name,
                "description": "Frontend E2E adversarial verifier agent",
                "system_prompt": "You are a helpful assistant.",
                "is_built_in": False,
                "skill_ids": [],
                "mcp_ids": [],
                "engine_params": {"adversarial_verification": True},
            },
        )
        create_resp.raise_for_status()
        return str(create_resp.json()["data"]["id"])


async def ensure_control_agent_exists() -> str:
    """Agent profile without adversarial verification (negative control)."""
    agent_name = "E2E Control Agent (No Verifier)"
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
        listing = await client.get("/api/v1/user-agents", params={"page": 1, "page_size": 100})
        listing.raise_for_status()
        payload = listing.json()
        agents = payload.get("data", payload if isinstance(payload, list) else [])
        if isinstance(agents, dict) and "items" in agents:
            agents = agents["items"]
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = str(agent["id"])
                await client.put(
                    f"/api/v1/user-agents/{agent_id}",
                    json={"engine_params": {"adversarial_verification": False}},
                )
                return agent_id

        create_resp = await client.post(
            "/api/v1/user-agents",
            json={
                "name": agent_name,
                "description": "Frontend E2E control agent without adversarial verifier",
                "system_prompt": "You are a helpful assistant.",
                "is_built_in": False,
                "skill_ids": [],
                "mcp_ids": [],
                "engine_params": {"adversarial_verification": False},
            },
        )
        create_resp.raise_for_status()
        return str(create_resp.json()["data"]["id"])


async def verify_agent_settings_toggle(
    page: Page,
    agent_id: str,
    *,
    expected_enabled: bool,
) -> None:
    """Open agent settings and confirm Adversarial Verifier switch state."""
    async with page.expect_response(
        lambda response: f"/api/v1/user-agents/{agent_id}" in response.url and response.request.method == "GET",
        timeout=60000,
    ) as agent_response_info:
        await _goto_with_retry(
            page,
            f"{FRONTEND_BASE}/settings/agents?agentId={agent_id}",
        )
    agent_response = await agent_response_info.value
    if agent_response.status != 200:
        raise RuntimeError(f"Failed to load agent settings profile: HTTP {agent_response.status}")

    capabilities_tab = page.get_by_role("button", name="Capabilities").or_(page.get_by_role("button", name="能力配置"))
    await capabilities_tab.first.click()
    await page.wait_for_timeout(800)

    await (
        page.locator("text=Advanced Engine Parameters")
        .or_(page.locator("text=高级引擎参数"))
        .first.wait_for(state="visible", timeout=45000)
    )
    label = page.get_by_text("Adversarial Verifier", exact=True)
    await label.scroll_into_view_if_needed()
    await label.wait_for(state="visible", timeout=15000)

    switch = (
        page.locator("div.flex.items-center.justify-between")
        .filter(has_text="Adversarial Verifier")
        .locator('button[role="switch"]')
    )
    await switch.wait_for(state="visible", timeout=15000)
    aria_checked = await switch.get_attribute("aria-checked")
    is_checked = aria_checked == "true"
    if is_checked != expected_enabled:
        raise RuntimeError(f"Adversarial Verifier toggle expected={expected_enabled}, actual={is_checked}")

    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
        profile = await client.get(f"/api/v1/user-agents/{agent_id}")
        profile.raise_for_status()
        engine_params = profile.json().get("data", {}).get("engine_params", {})
        api_flag = engine_params.get("adversarial_verification") is True
        if api_flag != expected_enabled:
            raise RuntimeError(
                f"Agent profile engine_params.adversarial_verification mismatch: expected={expected_enabled}, actual={api_flag}"
            )


async def submit_chat_message(page: Page, text: str) -> None:
    """Fill chat input and click Send (matches real user flow)."""
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)

    chat_input = page.locator("textarea[data-chat-input]")
    await chat_input.wait_for(state="attached", timeout=30000)
    await chat_input.click(force=True)
    await chat_input.fill(text)
    await page.wait_for_timeout(500)

    filled = await chat_input.input_value()
    if filled.strip() != text.strip():
        raise RuntimeError("Chat input value mismatch after fill()")

    send_btn = page.locator('form button[aria-label="Send"], form button[aria-label="发送"]')
    await send_btn.wait_for(state="visible", timeout=15000)
    await page.wait_for_function(
        """
        () => {
            const btn = document.querySelector(
                'form button[aria-label="Send"], form button[aria-label="发送"]',
            );
            return btn && !btn.hasAttribute('disabled');
        }
        """,
        timeout=15000,
    )
    await send_btn.click()


async def wait_for_assistant_text(
    page: Page,
    *,
    max_wait_s: int = 120,
    contains: str | None = None,
) -> str:
    """Wait until assistant message appears and streaming finishes."""
    saw_generating = False
    for _ in range(max(1, max_wait_s // 2)):
        await asyncio.sleep(2)
        try:
            is_generating = await asyncio.wait_for(
                page.evaluate(
                    """
                    () => {
                        const stopBtn = document.querySelector('button[aria-label="Stop"]');
                        if (stopBtn) return true;
                        const spinners = document.querySelectorAll('.animate-spin');
                        return spinners.length > 0;
                    }
                    """
                ),
                timeout=5.0,
            )
        except Exception:
            is_generating = False
        if is_generating:
            saw_generating = True
        try:
            assistant = page.locator('[data-test-id="assistant-message"]').last
            if await asyncio.wait_for(assistant.count(), timeout=5.0) > 0:
                text = (await asyncio.wait_for(assistant.inner_text(), timeout=5.0)).strip()
                if text and (contains is None or contains.lower() in text.lower()):
                    if not is_generating:
                        return text
        except Exception:
            pass
        if saw_generating and not is_generating:
            try:
                assistant = page.locator('[data-test-id="assistant-message"]').last
                if await asyncio.wait_for(assistant.count(), timeout=5.0) > 0:
                    text = (await asyncio.wait_for(assistant.inner_text(), timeout=5.0)).strip()
                    if text and (contains is None or contains.lower() in text.lower()):
                        return text
            except Exception:
                pass
    return ""


async def select_chat_model(page: Page) -> None:
    if "agent_id=" not in page.url and not page.url.rstrip("/").endswith(FRONTEND_BASE):
        await _goto_with_retry(page, f"{FRONTEND_BASE}/")
        await page.wait_for_load_state("domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1000)

    model_btn = page.locator("button").filter(has_text="Model").or_(page.locator("button").filter(has_text="模型"))
    if await model_btn.count() > 0:
        await model_btn.first.click()
        await page.wait_for_timeout(500)
        model_item = page.get_by_text(BASIC_MODEL_NAME, exact=False)
        if await model_item.count() > 0:
            await model_item.first.click()
            await page.wait_for_timeout(500)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
