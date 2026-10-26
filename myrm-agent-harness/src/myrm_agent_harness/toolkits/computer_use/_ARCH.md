# computer_use/

## Overview
Semantic Desktop Control (SDC) toolkit. Enables AI agents to snapshot and interact
with native desktop applications via accessibility trees (@dref) with coordinate vision fallback.
Detailed design: [DESKTOP_SYSTEM.md](DESKTOP_SYSTEM.md).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Exports create_desktop_tools, create_desktop_session, exclude_capture_windows | ✅ |
| types.py | Config | Shared types: ComputerAction, DesktopInteractAction, ScreenInfo, ActionResult, PermissionStatus, ExecutionMode, ForegroundPermissionCallback, ScreenUnlockCallback, ComputerUseConfig | ✅ |
| capture_probe.py | Core | PNG capturable probe (center-sample non-black/white) for PermissionStatus.screen_recording_capturable | ✅ |
| capture_exclusion.py | Core | `exclude_capture_windows(session, titles)`: hands a host's overlay window titles to the backend that captures the screen, resolving the `CuaDriverBackend` → native fallback chain inside the package so hosts never reach into private attributes; `False` = no capable backend (e.g. Linux) | ✅ |
| capture_title_contracts.py | Core | `SNAPSHOT_ONLY_EXCLUDED_CAPTURE_TITLES`: click-through OS overlays excluded from full-screen captures only (aligned with desktop window titles) | ✅ |
| app_identity.py | Core | Stable trust keys: `resolve_trust_key`, `trust_key_matches` (bundle_id / win exe / linux app id) | ✅ |
| iphone_mirror.py | Core | iPhone Mirroring (`com.apple.ScreenContinuity`) probe (`probe_iphone_mirror_state`), viewport bounds & state gate | ✅ |
| safety.py | Core | Blocked key combos (`+`/`-` tokenized like cua-driver), operator-as-key rejection (lone `*`/`/`/`+`/`-`/`%`/`=`), dangerous type-text guardrails, sensitive app guard (incl. terminal/shell + SelfAppGuard via bundle_id / host names), iPhone Mirroring connect popup guard, lock-screen & physical sleep hard interruption (owns the model-facing refusal wording for an unusable screen — `SCREEN_LOCKED_REFUSAL` / `DISPLAY_SLEEPING_REFUSAL` for input, `SNAPSHOT_*_REFUSAL` for snapshots — reused by `ScreenGuard`), foreground permission classification | ✅ |
| semantic_gate.py | Core | Control-level semantic risk gate (SSOT lexicon: `core/security/detection/semantic_risk.py`): AX interact gate (`enforce_desktop_interact_guard`) + vision coordinate gate with bbox reverse-lookup (`enforce_desktop_vision_guard`, `resolve_coordinate_target`), both fail-closed HITL interrupts with screenshot evidence + red-circle highlight payload | ✅ |
| screen_detector.py | Core | Microsecond native desktop lock-screen & sleep detection (Quartz C-API / OpenInputDesktop / loginctl) with 200ms throttling cache; `hid_idle_seconds()` human-presence primitive (seconds since the last hardware input event, macOS only, uncached, `None` = unknown) | ✅ |
| screen_guard.py | Core | `ScreenGuard`: the single lock / sleep gate of `ComputerSession` and `DesktopSession`; a locked probe first gives the host-registered `ScreenUnlockCallback` one chance, then the re-probe alone decides | ✅ |
| screenshot_processor.py | Core | Binary-search downsampling pipeline | ✅ |
| coordinate_scaler.py | Core | DPI-aware coordinate transformer | ✅ |
| som_overlay.py | Core | SOM numbered overlay on JPEG; agent path when `include_screenshot=True`, inspector refresh when screenshot captured; stable [N]↔@dref map (cap 80) | ✅ |
| session.py | Core | ComputerSession orchestrator (coordinate I/O, app + foreground gates, operation-scoped foreground waiver) | ✅ |
| desktop_session.py | Core | DesktopSession: AX snapshot, @dref registry, action lock serialization, self-healing remedy hints, shared approval revalidation, iPhone Mirroring connect-prompt gate (interact hard-deny / vision probe gate / snapshot gate banner), DESKTOP_VIEW_UPDATE, export_inspector_snapshot | ✅ |
| desktop_agent_tools.py | Core | 3 LangChain tools: snapshot / interact / vision | ✅ |
| envelope.py | Core | Intent envelope contracts (`IntentEnvelopeSpec`), keystroke sanitizer (`KeystrokeSanitizer`), modal window trust hierarchy, and boundary checker (`check_envelope_action`) | ✅ |
| mcp_server.py | Surface | MCP server adapter exposing desktop tools (DesktopMCPServer, register_desktop_mcp_tools) to external agents | ✅ |

| Submodule | Description |
|-----------|-------------|
| backends/ | Platform I/O: macOS, Windows, Linux |
| perception/ | AX tree capture, incremental diff, overlay role SSOT, renderer, ax_dispatch — see [perception/_ARCH.md](perception/_ARCH.md) |
| execution/ | BBox click healer fallback — see [execution/_ARCH.md](execution/_ARCH.md) |
| dref/ | @dref types, registry, errors (internal submodule) |
| recording/ | Desktop workflow skill recording, event clustering, Tool Lifting & SKILL.md synthesis — see [recording/_ARCH.md](recording/_ARCH.md) |

## Architecture

```
Agent → desktop_agent_tools (3 tools)
          → DesktopSession (semantic orchestrator)
              → DRefRegistry (@dref)
              → perception/ (AX snapshot + invoke)
              → execution/healer (bbox fallback)
              → ComputerSession (screenshot + coordinate I/O)
                  → CuaDriverBackend (background input proxy, optional)
                      → cua-driver MCP (SkyLight SPIs / Touch Injection)
                  → ComputerBackend (Protocol: macOS / Windows / Linux)
```

## Tool Surface

| Tool | Purpose |
|------|---------|
| desktop_snapshot_tool | AX tree with @dref IDs and app/window header; optional screenshot |
| desktop_interact_tool | Semantic action on @dref (click/fill/set_value/type/fill_credential/press/…) |
| desktop_vision_tool | Explicit screenshot/coordinate fallback |

## Key Design Decisions
    
1. **Semantic-first**: AX/UIA/AT-SPI tree → @dref interact; vision only when AX is empty
2. **View updates**: `desktop_snapshot` emits `DESKTOP_VIEW_UPDATE` via ToolProgressSink for frontend Desktop Inspector
3. **Safety in session**: Blocked key combos (macOS + Windows); operator-as-key rejection for lone printable operators (`* / + - % =`) on vision `key` **before** FG/screenshot revalidation; approval batch processor auto-denies the same args **before HITL** (`operator_as_key_deny_message`); dangerous type-text patterns (also pre-FG); sensitive application guard (`is_sensitive_app`, including terminal/shell apps). Enforced in `desktop_snapshot`, `desktop_interact`, `desktop_vision_action`, and approval middleware
4. **Multimodal responses**: Vision capture/actions return text + JPEG image blocks
5. **Platform auto-detection**: reuses `detect_platform()` from code_execution
6. **Security & Re-validation**: shared `_revalidate_if_stale_after_approval()` after approval delay — interact verifies @dref; vision refreshes screenshot/scaler
7. **Credential Vault integration**: `fill_credential` resolves secrets without exposing them in LLM context
8. **Permission probing**: `check_permissions(probe_capture=False|True)` — default grant-only; `probe_capture=True` sets `screen_recording_capturable`. Doctor always probes capture; Inline first paint is grant-only, Recheck uses `?probe_capture=true` (also on verified tone to re-probe stale grants). `all_granted` = OS grants only; `capture_ready` is True **only** when `capturable is True` (None = not probed ≠ ready). Missing Pillow ⇒ capturable False (cannot verify). Inline four-state UX: verified / unverified (`capturable is None`) / capture_failed (`grants OK` + `capturable is False`, title must not say “missing permissions”) / missing (OS grants incomplete). While `loading`, shell uses muted/neutral tokens (not missing amber). Windows deeplinks point at OS/docs URLs only.
9. **Native API routing hints**: `inspect_foreground()` appends AppleScript/COM/D-Bus hints in snapshot recommendation text
10. **Background input (cua-driver)**: optional focus-free input proxy
11. **Desktop control gate**: `check_app_approval` on interact and vision mutating actions; uses snapshot meta or `inspect_backend()` fallback; `check_foregroundPermission` for coordinate/healer paths with operation-scoped waiver after app approval. Server `DesktopControlGate` via `ForegroundPermissionCallback` (empty app fail-closed). LOCAL `background_strict`; sandbox auto-grants. SSE `desktop_control_approval_request` opens Desktop Inspector; resolve `POST /webui/desktop/approval/resolve`. Persist `{workspace}/.agent/desktop_control/approved_apps.json` keyed by stable `app_id` when available; list/revoke via `GET/DELETE /webui/desktop/trust/apps`
12. **Session lifecycle**: `ComputerSession.close()` on agent session end
13. **Action Serialization & Self-Healing**: `DesktopSession` enforces session-level concurrency control via `asyncio.Lock()`, serializing mutating desktop actions (`desktop_interact`, `desktop_vision_action`) while keeping AX snapshots non-blocking. Stale references (`DRefStaleError`) and invocation/fallback failures return structured `[REMEDY_HINT: ...]` to guide LLM self-healing without hallucinated retries.
14. **Human Takeover Gate & Hard Refusal**: whether a person drives the desktop is the process-wide `UserControl` (`utils/runtime/user_control.py`); `ComputerSession` / `DesktopSession` only consult it (`user_control`, `observed_generation`), nothing is pushed into sessions. `create_desktop_tools` fences all three desktop tools behind it: while a person drives, every tool waits; afterwards `desktop_interact_tool` and any `desktop_vision_tool` action other than `capture`/`screenshot` return a "look again" notice until `desktop_snapshot_tool` or a vision capture has succeeded. Session-level `_ensure_not_user_takeover()` still guards every mutating session call (`click_at`, `type_text`, `key_press`, `desktop_interact`, ...) and raises `UserControlTimeoutError` after 600s, so the desktop stays locked rather than act behind the person's back. A tool waiting on a person is not inside a cancel boundary: Stop takes effect once control returns, the takeover lease expires or the 600s cap is hit, and the action it was about to run is refused by the rule above. The fence is tool-level: it does not stop processes the agent started itself (bash).
15. **Intent Envelope & Non-Interruptive Runner**: Pre-flight consent envelope establishes a bound on target applications, maximum lease steps, and sensitive key sanitization. Actions strictly inside the envelope bypass repetitive approval popups, dynamically escalating to approval only on boundary overflow or quota exhaustion.
16. **Desktop Lock-Screen Guardian & Physical Sleep Gate**: Real-time OS-level detection of lock screen and display sleep states (macOS Quartz `CGSessionCopyCurrentDictionary`, Windows `OpenInputDesktop`, Linux `loginctl LockedHint`, headless/CI auto-bypass). Microsecond-level hard refusal on all mouse/keyboard inputs (`ScreenLockedInterruptionError`), snapshot redaction to prevent multimodal LLM hallucination loops on black/login screens, and `reanchor_visual_state()` self-healing on unlock. All gates go through `ScreenGuard` (`screen_guard.py`). The harness never unlocks a screen itself: a host may register a `ScreenUnlockCallback` via `set_screen_unlock_callback()`, which is awaited once when a guarded action finds the screen locked (on-demand unlock). The guard then re-probes and trusts only that probe, so a host that claims success on a still-locked screen cannot open the gate and a failing host leaves the refusal unchanged. A successful recovery discards pre-lock visual state (`DRefRegistry.clear()` turns every earlier @dref stale, forcing a fresh snapshot). Sleeping displays are not the host's to fix and stay refused.
17. **Overlay-aware pointer guard (macOS)**: when the host injected excluded-capture window titles through `exclude_capture_windows` (a privacy overlay is up), global-HID coordinate pointer actions (`click` / `mouse_move` / `scroll` / `drag`) hit the topmost window — the overlay — instead of the target app, and the overlay reads the synthetic event as a passer-by touch. `MacOSBackend._pointer_occluded()` therefore fails closed (`ActionResult(success=False)` with a `[REMEDY_HINT]` pointing at `@dref` / keyboard actions) while an overlay window is on screen. PID-targeted delivery (`has_input_target()`), keyboard actions, sessions without injected titles, cua-driver's own background input, and other platforms are unaffected; when `CuaDriverBackend` falls back to the native backend, the fallback path inherits the guard. The same title set drives full-screen capture exclusion and this guard, so only an overlay that captures clicks may be named; a click-through overlay must stay out of the set or it would block the agent's own pointer actions.

## Key Dependencies

- `dref/` (@dref registry submodule)
- `utils/runtime/user_control` (process-wide human-control hold + tool gate)
- `core/security/credential_vault` (fill_credential vault resolution)
- `code_execution` (platform detection)
- `PIL`, `pyautogui`, platform AX libraries (see backends/)
- `cua-driver` (optional, background input on macOS/Windows/Linux)
