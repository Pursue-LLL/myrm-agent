# desktop_session/

## Overview
`DesktopSession`: semantic desktop control (AX snapshot, @dref registry, interact, vision fallback, WebUI view payloads) on top of `ComputerSession`. The behaviour is split into single-purpose mixins that `core.py` composes; the package facade exports `DesktopSession` and `create_desktop_session`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Facade | Exports `DesktopSession`, `create_desktop_session` | ✅ |
| core.py | Core | `DesktopSession` aggregate root: owns the registry, the snapshot clock and the action lock, composes the mixins; `create_desktop_session` | ✅ |
| host.py | Contract | `DesktopSessionHost`: typed host of the mixins (state + stubs of the methods they call on each other); type-checking only, `object` at runtime; `ViewUpdateCallback` | ✅ |
| adopt.py | Core | `_adopt_capture`: the single write entry of the @dref registry (sensitive-app guard, then `DRefRegistry.adopt`, then the diff against the content it replaced); `Adoption` | ✅ |
| snapshot.py | Core | `desktop_snapshot`: screen guard, registration of the capture through `_adopt_capture`, diff or full tree, optional SoM screenshot | ✅ |
| interact.py | Core | `desktop_interact`: per-app approval, revalidation, semantic gate, credential fill, native action with bbox fallback, follow-up snapshot | ✅ |
| vision.py | Core | `desktop_vision_capture` (screen guard and sensitive-app guard, then the screenshot; shared by the agent tool and the MCP tool), `desktop_vision_action` (argument safety, sensitive-app, mirror, approval and semantic gates before any pixel is touched), `_foreground_identity` (the one foreground probe both use), `_build_multimodal_response` | ✅ |
| views.py | Core | `DESKTOP_VIEW_UPDATE` emission, inspector exports (`export_registry_view`; `export_inspector_snapshot`, which registers its capture through `_adopt_capture` and answers an empty payload for a blocked app), SoM annotation, `refs_for_view_update` (refs as the overlay payload; `nth` from the SoM map) | ✅ |
| guards.py | Core | `_revalidate_if_stale_after_approval` (re-read the screen when an approval delayed the action, register it through `_adopt_capture`, refuse when the approved @dref has no counterpart in it), `_capture_guard_screenshot` (evidence for the semantic gate's approval cards) | ✅ |

## Dependencies

- `computer_use/session.py` (POS: `ComputerSession` base: screen guard, app approval, screenshots, coordinate input)
- `computer_use/dref/` (POS: registry, element and snapshot types, errors)
- `computer_use/perception/` (POS: `capture_snapshot`, `invoke_element`, `inspect_backend`, renderers, diff)
- `computer_use/execution/healer.py` (POS: bbox fallback of `desktop_interact`)
- `computer_use/safety.py`, `semantic_gate.py`, `iphone_mirror.py`, `som_overlay.py`
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

The registry changes through one path only: a capture (agent snapshot, approval revalidation, inspector refresh) goes to `_adopt_capture`, which refuses a capture of a sensitive application before anything is registered and otherwise calls `DRefRegistry.adopt`. `adopt` issues the ids: they only grow, a retired id is never given to another element, and an element keeps its id across captures only when it is in the same application (name and process) and its non-empty (role, name) is unique on both sides. `Adoption.diff` compares the new content with the replaced one by id, so a diff-mode snapshot lists new elements, changed elements and retired ids, and states that every unlisted id is still valid. A retired id fails as stale instead of resolving to a neighbour.

Module-level collaborators (`capture_snapshot`, `invoke_element`, `try_bbox_click`, `inspect_backend`, `render_snapshot_tree`, `probe_iphone_mirror_state`) are imported where they are called, so a test patches `...desktop_session.<module>.<name>` of the mixin that calls it: `snapshot` (snapshot flow), `guards` (approval revalidation), `views` (inspector export), `interact`, `vision`.

Detailed design: [DESKTOP_SYSTEM.md](../DESKTOP_SYSTEM.md)
