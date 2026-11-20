# desktop_session/

## Overview
`DesktopSession`: semantic desktop control (AX snapshot, @dref registry, interact, vision fallback, WebUI view payloads) on top of `ComputerSession`. The behaviour is split into single-purpose mixins that `core.py` composes; the package facade exports `DesktopSession` and `create_desktop_session`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Facade | Exports `DesktopSession`, `create_desktop_session` | ✅ |
| core.py | Core | `DesktopSession` aggregate root: owns the registry, the secrets the vault filled, the snapshot clock and the action lock, composes the mixins; `create_desktop_session` | ✅ |
| host.py | Contract | `DesktopSessionHost`: typed host of the mixins (state + stubs of the methods they call on each other); type-checking only, `object` at runtime; `ViewUpdateCallback` | ✅ |
| adopt.py | Core | `_adopt_capture`: the single write entry of the @dref registry (sensitive-app guard, masking of the controls that hold a vault-filled secret, then `DRefRegistry.adopt`, then the diff against what the model was last shown); `Adoption` | ✅ |
| secrecy.py | Core | `FilledSecrets`: the secrets the vault filled into controls of the session; `redact` replaces them in a text (the backend errors a reply quotes), `mask` in every control value of a capture, wherever they occur in the value | ✅ |
| snapshot.py | Core | `desktop_snapshot`: screen guard, registration of the capture through `_adopt_capture`, diff or full tree, optional SoM screenshot; the only place that records what the model was shown (`DRefRegistry.mark_shown`) | ✅ |
| interact.py | Core | `desktop_interact`: per-app approval, revalidation, semantic gate, credential fill (the secret is remembered before delivery and redacted from the backend errors a reply quotes), native action, follow-up snapshot; after the re-read the gates, the delivery and the follow-up snapshot use the one capture the registry resolved the element from. Only an unsupported native action falls back to the bbox click, and a text entry that falls back passes the semantic gate once more as the click it becomes; a stale or unknown outcome is reported and neither retried nor clicked | ✅ |
| vision.py | Core | `desktop_vision_capture` (screen guard and sensitive-app guard, then the screenshot; shared by the agent tool and the MCP tool), `desktop_vision_action` (argument safety, sensitive-app, mirror, approval and semantic gates before any pixel is touched), `_foreground_identity` (the one foreground probe both use), `_build_multimodal_response` | ✅ |
| views.py | Core | `DESKTOP_VIEW_UPDATE` emission, `_view_payload` (the one payload shape of every view), inspector exports that only observe (`export_registry_view`: the registry's elements over a current display-only screenshot, no AX read, no registry write; `export_inspector_snapshot`, the manual refresh: a capture registered through `_adopt_capture` under `_action_lock`, an empty payload for a blocked app, the registry view while an action holds the lock or the screen is locked or asleep), SoM annotation, `refs_for_view_update` (refs as the overlay payload; `nth` from the SoM map) | ✅ |
| guards.py | Core | `_revalidate_if_stale_after_approval` (when an approval delayed the action, re-read the application of the approved @dref by name; refuse when it has no readable window or another application or process answers, otherwise register the capture through `_adopt_capture` and refuse when the approved @dref has no counterpart in it), `_capture_guard_screenshot` (evidence for the semantic gate's approval cards) | ✅ |

## Dependencies

- `computer_use/session.py` (POS: `ComputerSession` base: screen guard, screenshots, coordinate input; its app and foreground approval comes from `session_permissions.py`)
- `computer_use/dref/` (POS: registry, element and snapshot types, errors)
- `computer_use/perception/` (POS: `capture_snapshot`, `invoke_element` with its `AxInvokeResult` failure classes, `inspect_backend`, `run_ax_call` (awaits them off the event loop on macOS), renderers, diff)
- `computer_use/execution/healer.py` (POS: bbox fallback of `desktop_interact` for an unsupported native action)
- `computer_use/safety.py`, `semantic_gate.py`, `iphone_mirror.py`, `som_overlay.py`, `coordinate_scaler.py` (POS: maps element boxes onto the screenshot the inspector shows)
- Used by `desktop_agent_tools.py`, `mcp_server.py` and the server's desktop routes and gateway (all through the facade)

## Architecture Overview

```
DesktopSession (core.py)
  ├─ DesktopInteractMixin   interact.py
  ├─ DesktopVisionMixin     vision.py
  ├─ DesktopSnapshotMixin   snapshot.py
  ├─ DesktopViewMixin       views.py
  ├─ DesktopGuardSupportMixin  guards.py
  ├─ DesktopRegistryMixin   adopt.py
  └─ ComputerSession        ../session.py   (last base, so the runtime MRO is the mixins, then the session base)
```

Every mixin derives from `DesktopSessionHost`, which is `object` at runtime and the typed contract for mypy. The cross-mixin calls are `desktop_snapshot` (interact), the two guard methods (interact, vision), the view emitters plus SoM annotation (snapshot) and `_adopt_capture` (snapshot, guards, views); their signatures are declared once in `host.py`, so a drift fails type checking.

## @dref registry writes

The registry changes through one path only: a capture (agent snapshot, approval revalidation, the user's manual inspector refresh) goes to `_adopt_capture`, which refuses a capture of a sensitive application before anything is registered and otherwise calls `DRefRegistry.adopt` with the capture masked by `FilledSecrets` (a credential the vault filled is replaced by `[REDACTED]` wherever it occurs in a control value, so the follow-up snapshot, later snapshots, the diff and the inspector never show it). `adopt` issues the ids: they only grow, a retired id is never given to another element, and an element keeps its id across captures only when it is in the same application (name and process). Inside that application a non-empty (role, name) that is unique on both sides continues wherever the element moved, and any other element continues only while its (role, name, bbox) is unique on both sides, that is, while it did not move. `Adoption.diff` compares the new content by id with what the model was last shown (`desktop_snapshot` records it), not with the previous capture, so a diff-mode snapshot lists new elements, changed elements and retired ids, including those that changed during a re-read the model did not ask for, and states that every unlisted id is still valid. A retired id fails as stale instead of resolving to a neighbour.

The approval revalidation re-reads the application of the approved @dref by name (not the foreground application) and refuses before registering anything when it has no readable window or another application or process answers. After the re-read the semantic gates, the mirror gate, the delivery and the follow-up snapshot all use the one capture the registry resolved the element from.

## Inspector observation

The WebUI inspector observes and never rewrites what the agent holds. `export_registry_view` (the automatic refresh after a tool ends or an approval card opens) reads the registry and draws it over a current screenshot: no accessibility read, no registry write, no view emitted, and it does not wait for `_action_lock`. The screenshot is made for display only (`_observe_screen`), so `ComputerSession._scaler` and the last image stay as the agent's last screenshot left them, and a locked screen or a sleeping display yields no image without ever asking the host to unlock it (passive `ScreenGuard.is_locked` / `is_sleeping` probes, not `refusal`). `export_inspector_snapshot` (the manual refresh) is the only inspector path that reads the application in front: it holds `_action_lock`, so it cannot interleave with an action, and it registers the capture through `_adopt_capture` (a blocked application is refused). While an action holds the lock, which an approval keeps for as long as the user deliberates, or while the screen is unusable, it answers the registry view and writes nothing. Both exports return None when the agent has registered nothing.

Every wait on the platform accessibility API (the capture of a snapshot, of an approval re-read and of the manual inspector refresh; the native invoke; the foreground identity; the iPhone Mirroring probe) goes through `run_ax_call`, which runs it on a worker thread for the macOS backend so the event loop keeps serving other chats. Only that read is awaited off the loop: the capture is registered (`_adopt_capture`) and the view is emitted back on the loop thread, so the registry has one writer thread.

Module-level collaborators (`capture_snapshot`, `invoke_element`, `try_bbox_click`, `inspect_backend`, `render_snapshot_tree`, `probe_iphone_mirror_state`) are imported where they are called, so a test patches `...desktop_session.<module>.<name>` of the mixin that calls it: `snapshot` (snapshot flow), `guards` (approval revalidation), `views` (inspector export), `interact`, `vision`.

Detailed design: [DESKTOP_SYSTEM.md](../DESKTOP_SYSTEM.md)
