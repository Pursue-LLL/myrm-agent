# Semantic Desktop Control (SDC) System Design

> Hybrid native desktop automation: accessibility tree + @dref semantic interact, with explicit coordinate vision fallback.

---

## Design Goals

1. **Agent-friendly**: @dref element references from AX/UIA/AT-SPI trees reduce token cost vs full-screen screenshots every step; incremental diff re-sends only the changed refs in continuous-interact scenarios
2. **Semantic-first**: Prefer `desktop_interact_tool(ref=@dref)` over coordinate guessing
3. **Explicit fallback**: `desktop_vision_tool` for canvas-only UIs, empty AX trees, or failed semantic invoke
4. **WebUI parity**: Mirror browser inspector via `DESKTOP_VIEW_UPDATE` SSE + `/webui/desktop/snapshot` REST refresh
5. **Safety**: Four guardrail types in `safety.py` — blocked key combos (macOS + Windows), operator-as-key rejection (lone `*`/`/`/`+`/`-`/`%`/`=` on vision `key`), dangerous type-text patterns, and sensitive application guard (`is_sensitive_app`, including terminal/shell apps and SelfAppGuard for Myrm/Cursor host UI via bundle_id + host names). Enforced in `desktop_snapshot`, `desktop_interact`, `desktop_vision_action` and the screenshot entry `desktop_vision_capture` (which also refuses while the screen is locked or asleep, worded as "cannot view"). On top of these, `semantic_gate.py` adds control-level destructive-action HITL: both `desktop_interact` (AX @dref actions) and `desktop_vision_action` (coordinate clicks, via bbox reverse-lookup to the smallest containing element) classify the target against the shared risk lexicon SSOT (`core/security/detection/semantic_risk.py`) and interrupt with fail-closed HITL evidence (screenshot + red-circle highlight) before any high-risk activation. Every `desktop_interact` action except text entry (`fill`, `set_value`, `type`, `fill_credential`) counts as an activation (`hover` and `focus` are delivered as the control's press), so a verb nobody classified is gated too, and a text entry the native route declines is gated once more as the click the bbox fallback delivers

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LangChain Tools (3)                      │
│  desktop_snapshot | desktop_interact | desktop_vision       │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    DesktopSession                           │
│  ┌──────────────┬──────────────┬──────────────┬──────────┐ │
│  │ DRefRegistry │ perception/  │ execution/   │Computer  │ │
│  │  (@dref)     │ AX capture   │ bbox healer  │Session   │ │
│  └──────────────┴──────────────┴──────────────┴──────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│      CuaDriverBackend (optional, macOS / Windows / Linux)     │
│  Background input via cua-driver MCP (focus-free)           │
│  PID re-resolved per operation; fallback on any error       │
│  ComputerSession.close() releases MCP subprocess on exit   │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              ComputerBackend (macOS / Windows / Linux)        │
│  Screenshot + coordinate I/O via Quartz CGEvent / pyautogui / xdotool │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflow

```
desktop_snapshot_tool
    ↓ AX tree with @dref IDs, app/window header (+ optional screenshot with [N] SOM labels) + browser soft-routing hint
desktop_interact_tool(ref=@dref, action=...)
    ↓ per-app approval gate → AX invoke → bbox click only after an unsupported native action → incremental diff follow-up (full-view fallback when unreliable)
desktop_vision_tool (only when AX empty or interact failed)
    ↓ per-app approval gate → foreground permission gate → stale refresh → coordinate actions
```

### @dref identity

Platform captures name their elements by position (`d0`, `d1`, ...), and a position shifts whenever a row appears above it. The registry therefore issues the ids itself (`DRefRegistry.adopt`, called only from `DesktopSession._adopt_capture`): ids only grow and are never reused, and an element keeps its id across captures only when it is in the same application (name and process). Inside that application a non-empty (role, name) that is unique on both sides continues wherever the element moved, and any other element (unnamed, or one of several twins) continues only while its (role, name, bbox) is unique on both sides, that is, while it did not move. Every other element gets a fresh id, and an id that was not carried over is stale: it fails with a `[REMEDY_HINT]` instead of resolving to a neighbour. A diff-mode snapshot is computed against what the model was last shown, lists new, changed and retired ids, and states that every unlisted id is still valid. `_adopt_capture` also runs the sensitive-application check, so the agent snapshot, the approval revalidation and the inspector refresh cannot register the elements of a blocked application.

When an approval delays an action, `desktop_interact` re-reads the application of the approved @dref by name (not the foreground application). If the application has no readable window, or another application or process answers, the action is refused and the registry stays as the model saw it; otherwise the semantic gates, the mirror gate, the delivery and the follow-up snapshot all use the capture the element was resolved from.

### Failure classes of a native action

A native action that failed reports what it proves about delivery (`perception/ax_result.py`), and `desktop_interact` acts on that class alone. **Unsupported** (no permission, no such action, no editable text): nothing reached the element, so the bbox click takes over (for a text entry, which clicks the element before it types, only after the destructive-control gate a click passes). **Stale** (the element or its window is gone or changed): the old coordinates may belong to something else, so nothing is clicked and the model is told to read the application again. **Unknown** (timeout, killed script, an exception during the action): the action may have been delivered, so it is neither retried nor clicked, and the model is told to check the screen before repeating it. macOS classifies by the AppleScript error number because the message text is localized; see `perception/_ARCH.md`.

### Credential fill

`fill_credential` takes the secret from the vault and never from the model, but the control that holds it reports it as its value in the next capture, and the follow-up snapshot is part of every `desktop_interact` reply. The session therefore remembers each secret the vault filled (`desktop_session/secrecy.py`, the vault's own strings) from before the delivery, and `_adopt_capture` replaces it with `[REDACTED]` wherever it occurs in a control's value, not only when it is the whole value, because typing does not always replace what the control held (a retried fill, or text typed at the caret on Windows and in the bbox fallback). The follow-up snapshot, a later snapshot, the diff, the registry and the inspector all read the masked value. A backend error that a reply quotes (native failure, bbox fallback failure) is redacted the same way. A secret the page shows only in pieces, or as an image, is not recognized. On Windows a text entry goes to `SendKeys` as the key script that types the value literally (`{` as `{{}`, `}` as `{}}`), because a brace in a value would otherwise be read as a key name such as `{Win}`.

### Event loop and foreground read

Every AX capture, element invoke, foreground read and iPhone Mirroring probe of the macOS backend waits on an `osascript` child for up to 15 s, and run on the loop thread that wait stops every other chat of the process (streaming, approvals, heartbeats). `perception/ax_dispatch.py::run_ax_call` therefore runs it on a worker thread for the macOS backend only. The calls touch no in-process AppKit state, and the caller keeps the registry write (`_adopt_capture`) on the loop thread by awaiting the read alone. The Windows and Linux bindings are called inline: the thread rules of UIA (COM) and AT-SPI are not verified. The focus-leak guard of the coordinate fallback (`guard_foreground`) reads the front-most layer-0 window of the window server's stacking order, because NSWorkspace only hears focus changes through an AppKit run loop, which the server process does not run.

---

## Core Components

| Component | Location | Role |
|-----------|----------|------|
| `DesktopSession` | `desktop_session/` | Orchestrator: registry, snapshot, interact, vision, view updates (one mixin per entry point, composed in `core.py`) |
| `create_desktop_tools` | `desktop_agent_tools.py` | LangChain tool factory |
| `DRefRegistry` | `computer_use/dref/registry.py` | Session-scoped @dref map that issues never-reused ids and carries an id across snapshots only for an identifiable element |
| `perception/` | `ax_dispatch.py`, `ax_diff.py`, platform AX | Capture AX tree, incremental diff, invoke elements |
| `recording/` | `synthesizer.py`, `capture_driver.py` | Skill synthesis from events, and `DesktopCaptureDriver`: polls the AX tree, diffs frames into click / type / window-focus events (skipping sensitive apps) |
| `execution/healer.py` | BBox click fallback | When the native route cannot perform the action; never after a stale or unknown outcome |
| `_action_lock` | `desktop_session/core.py` | Session-level async mutex | Serializes mutating interact/vision actions and the Inspector's manual refresh |
| `[REMEDY_HINT]` | `desktop_session/interact.py`, `desktop_session/vision.py` | Self-healing diagnosis | Structured recovery guidance for stale refs and execution failures |
| `ComputerSession` | `session.py` | Screenshot + coordinate I/O |
| `backends/` | Platform I/O | macOS, Windows, Linux |

---

## Platform Support

| Platform | AX Snapshot | AX Invoke | Vision Fallback |
|----------|-------------|-----------|-----------------|
| macOS | Accessibility API (targeted capture by app name; exact name with contains fallback; auto-fallback to foreground when not found) | ✅ (targeted invoke by app name) | ✅ |
| Windows | UI Automation (targeted capture by process name via shared `_locate_window`) | ✅ (targeted invoke shares `_locate_window`) | ✅ |
| Linux | AT-SPI (pyatspi; targeted capture scoped to a matching application) | ✅ (the key names an application instance; the found element must keep the snapshot's role and name) | ✅ |

> **Targeted scope** (`scope='target'` + `app_name`): captures the target app's main window tree without changing the foreground, on all three platforms. Snapshot and invoke share the same window-location logic on each platform so `@dref` indices stay consistent. When the target cannot be located the call signals it: macOS auto-falls back to the foreground (the header `scope` field reflects `foreground`), while Windows and Linux return an explicit "target window not found" error instead of silently returning the wrong window.

---

## Frontend Integration

| Channel | Payload |
|---------|---------|
| SSE `DESKTOP_VIEW_UPDATE` | screenshot_base64 (SOM-labeled when multimodal agent snapshot or inspector refresh), refs (BBox overlay + `nth` when SOM active), needs_permission |
| SSE `DESKTOP_CONTROL_APPROVAL_REQUEST` | Per-app / foreground approval card in Desktop Inspector: `request_id`, `operation` + `trust_key` bound `fingerprint`, `changed_since_last_grant` drift flag, `withdrawn` clear signal, `reason` (user deny reason surfaced) |
| REST `GET /webui/desktop/snapshot` | Same shape, always with `chat_id`. `source=registry` (automatic refresh: `desktop_*` TOOL_END, approval cards): the elements the agent last registered, numbered and drawn over the current screen. `source=live` (the refresh button): a new foreground capture. 404 `no_registry_snapshot` when there is nothing to show |
| REST `POST /webui/desktop/approval/resolve` | Resolve pending desktop control approval |
| Desktop Inspector | `DesktopLiveView` auto-opens on approval SSE; `DesktopControlApprovalBanner` for Allow/Deny |

Server wiring: `agent._desktop_session` → `AgentGateway.get_active_desktop_session()`.

The Inspector observes and never rewrites what the agent holds. The automatic refresh (`export_registry_view`) never reads the accessibility tree, never writes the registry and never emits a view; it draws the registry's elements over a current screenshot that is made for display only, so the scaler and last image that the coordinate actions convert the model's coordinates with stay as the agent left them. Only the user's manual refresh (`export_inspector_snapshot`) captures anew: it takes `_action_lock`, registers the capture through `_adopt_capture` (a blocked application is refused and drawn as an empty view), and while an action holds the lock (an approval keeps it for as long as the user deliberates) it answers the registry view and writes nothing. Both read the screen guard with its passive probes only: a locked screen or a sleeping display shows no image, and the host's on-demand unlock is never asked for. Deciding whether the application in front is blocked takes an accessibility read that the automatic refresh avoids, so its screenshot shows whatever is on the user's own screen: it is a display image that is not emitted on the event stream and that the frontend only draws in the Inspector panel and the approval card.

---

## Diagnostics

| Surface | Role |
|---------|------|
| `GET /webui/desktop/permissions` | OS grants by default; optional `?probe_capture=true` sets `screen_recording_capturable`. Response includes `all_granted` (grants only) and `capture_ready` (grants ∧ capturable is True). Temporary session closed after probe |
| `CuPermissionInline` (Agent config) | Four-state UX when `computer_use` is enabled locally: verified / grants-ok-unverified / capture_failed / missing (+ API error). capture_failed = grants OK but live probe failed (honest title). First load is grant-only; Recheck uses `probe_capture=true` |
| Settings Doctor `DesktopControl` probe | `check_desktop_permissions_health()` always runs `probe_capture=True`; PASS only when `PermissionStatus.capture_ready`; otherwise WARN for missing grants or `WARN_DESKTOP_CAPTURE_NOT_READY` |
| Server regression | `myrm-agent-server/tests/api/health/test_doctor.py::test_desktop_control_probe_in_doctor`; `tests/api/webui/test_desktop_permissions.py` (probe session close) |
| Frontend vitest | `DoctorDashboard.desktopControlWarn.test.tsx`; `CuPermissionInline.test.tsx`; `DesktopPermissionsCard.test.tsx` (5 cases); `DesktopControlApprovalBanner.test.tsx`; `DesktopLiveView.permissionBanner.test.tsx`; `lib/desktop/permissionDeepLink.test.ts` (6 files, 22 cases) |
| Deeplink SSOT | `myrm-agent-frontend/src/lib/desktop/permissionDeepLink.ts` |
| Open semantics | Settings `DesktopPermissionsCard` → `openPermissionDeepLink`（deeplink fallback）；Doctor / Agent inline / Inspector → `openPermissionDeepLinkWithGuideFallback(url, platform)`（平台指南 fallback） |
| Trusted apps | `GET/DELETE /webui/desktop/trust/apps` + Settings trusted-apps section（加载失败显示重试，不伪装空列表） |
| Chrome E2E | `tests/e2e/test_desktop_control_approval_chrome_e2e.py` + `tests/e2e/desktop_approval/` — allow_once / allow_session / allow_always→revoke；Darwin：`./myrm-dev test -m chrome_e2e_desktop …` |
| Chrome E2E attach gate | `tests/support/e2e_runtime_guard.py::assert_chrome_attach_health` — shared-attach lane only; item runtimes skip (private preflight already ran) |

Channel security: IM strips `!desktop_*`; Cron denies `desktop_capture` / `desktop_control` (see [SECURITY_SYSTEM.md](../../agent/security/SECURITY_SYSTEM.md)).

---

## Agent Prompt Rules

Injected via server `DESKTOP_CONTROL_RULES` (`myrm-agent-server/app/ai_agents/prompts/shared_rules.py`) when computer use tools are mounted (`mount_resolver.mount_computer_use`; the rules exist in English only, so every locale gets the same bytes and the prompt cache prefix stays stable):

- Workflow order: snapshot → interact
- Prefer @dref; use `set_value` for atomic field replacement; use vision only when AX is empty or interact failed
- Never pass printable operators (`*`, `/`, `+`, `-`, `%`, `=`) as `desktop_vision_tool` `key=` names — use `type` or click calculator/@dref; interact `press` activates the @dref control (not a keyboard key name). Runtime rejects lone operator tokens on vision `key` **before** FG/screenshot revalidation (display-independent) with REMEDY_HINT; approval middleware also auto-denies the same args **before HITL** so users never approve an always-rejected call.
- Targeted scope: to act on a specific app without changing the foreground, snapshot with `scope="target"` + `app_name`, then interact via its `@dref` refs
- Background batching: finish deterministic reversible steps in as few tool calls as possible — never stop mid-sequence to ask whether to continue; only stop for ambiguous identity, fresh coordinates, irreversible actions, or unexpected UI state
- Cheapest check first: visible state → one screenshot; semantic state → one AX query; use both only when they prove different things
- Poll inside the call: wait for async UI states by re-querying within the running tool call instead of asking the model round after round
- macOS permission: ask user to grant Accessibility (and event-posting access when prompted) before retry
- Per-app first approval via Web UI (`DesktopControlApprovalBanner`)
- Native API routing: snapshot recommendation may suggest `bash_code_execute_tool` for scriptable apps

---

## Known Limits

| Item | Status |
|------|--------|
| Linux AT-SPI invoke | ✅ implemented (pyatspi doAction/EditableText/grabFocus) |
| Event loop on Windows and Linux | ⏳ AX calls run inline on the loop thread, so a slow capture pauses the other chats of the process for its duration; macOS runs them on a worker thread (see "Event loop and foreground read") |
| Skill recording capture granularity | ⏳ `DesktopCaptureDriver` diffs foreground AX snapshots, so it observes interactions that change the tree: new elements (click), value changes on interactive roles (type on text entry, click on checkbox/radio/switch/slider), and app switches. Pointer gestures that leave no tree trace (drag, scroll, repeated clicks on an unchanged element) and modifier-key shortcuts (`Cmd+S`) are not captured. Event-driven capture via OS input taps (macOS CGEventTap / Windows SetWindowsHookEx / Linux XRecord) is the upgrade path |
| Desktop control gate (server) | ✅ `DesktopControlGate` + SSE approval card. Local monorepo: `./myrm-dev ready` (editable harness; no PyPI). Release/CI: harness tag → `./myrm-dev harness sync-lock` → commit `uv.lock` before `--frozen` |
| Unattended desktop (Locked Use + Privacy Curtain) | ✅ server `locked_use/` unlock 三态 + Tauri `curtain_capture_exclusion_ready`（Windows：`RtlGetVersion` build 探测，≥19041）+ 设置 fail-closed；单测 `tests/services/locked_use/`（169，`./myrm-dev test myrm-agent/myrm-agent-server/tests/services/locked_use/`） |
| Stream E2E tests | ⏳ `test_desktop_control_approval_chrome_e2e.py` + `tests/e2e/desktop_approval/` — `@pytest.mark.chrome_e2e_desktop`；allow_once / allow_session / allow_always→Settings revoke；**需 macOS + `./myrm-dev ready --chrome` + 后端宿主 Accessibility**（`runner.py` 启动时 `desktop_permissions()`，缺失即 `pytest.fail`；Screen Recording 缺失仅 progress 软告警）；单测 lane：`tests/unit/desktop_approval/`（121，`./myrm-dev test myrm-agent/myrm-agent-server/tests/unit/desktop_approval/`） |
| Onboarding hint when computer_use enabled | implemented (toggle + tooltip + empty state) |
| Native API routing hints | implemented (macOS/Windows/Linux) |
| Desktop browser E2E host grants | the `chrome_e2e_desktop` nodes probe the *backend host* process (`/webui/desktop/permissions`); a backend running in a background bootstrap context reports denied even when your shell has grants — run it from a GUI-session backend or grant TCC to the host |
| Background input (macOS) | ✅ implemented (PID-targeted delivery + foreground guard + window capture; minimized windows and Chromium move/scroll stay limited) |
| Visual approval OS red frame (Tauri) | ✅ macOS and Windows; other platforms: `show_visual_approval_overlay` returns Err + frontend `desktopBridge.isMacOS() \|\| isWindows()` gate (in-app approval card remains fallback) |
| Cloud-hosted sandbox (control plane) | Locked Use requires the user’s **local Tauri shell** on macOS; Privacy Curtain and the OS overlay require it on macOS or Windows. Cloud VMs have no user lock screen or Myrm desktop IPC — fail-closed; use in-app approval and browser/desktop inside the sandbox only. |

---

## References

- Browser parity: [BROWSER_SYSTEM.md](../browser/BROWSER_SYSTEM.md)
- Module index: [_ARCH.md](_ARCH.md)
