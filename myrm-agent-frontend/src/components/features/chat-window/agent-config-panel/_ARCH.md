# agent-config-panel/

## Overview

Agent profile editing UI: skills, MCP, built-in tools, browser options, security overrides.

## File Index

| File | Role | Description |
|------|------|-------------|
| `AgentConfigEditDialog.tsx` | Core | Full-screen/sheet editor; persists `enabled_builtin_tools`; sandbox `@/lib/builtin-tool-entitlements` strips ghost cron/computer_use after CP entitlements load |
| `AgentConfigPanel.tsx` | Core | Panel shell and preset shortcuts |
| `AgentConfigCards.tsx` | Core | Summary cards for active agent |
| `AgentBrickCard.tsx` | Core | Compact agent brick with tool badges |
| `SkillsSectionPanel.tsx` | Core | Skills selection panel in agent config editor |
| `SkillsSectionPanelParts.tsx` | Helper | NoiseGauge + skill zone subcomponents (`actionSpaceRadar.*` i18n) |
| `ActionSpaceAccuracyRadar.tsx` | Helper | Decision-accuracy forecast bar; Smart Prune calls `runCuratorSweep()` (real curator sweep, not is_core-only) |
| `AgentConfigSelectableCard.tsx` | Helper | Selectable card + add-more control for config sections |
| `BuiltinToolsPanel.tsx` | Core | Built-in tool toggles; sandbox cron/computer_use cards gated by `useFeatureEntitlements` (`canUseCron` / `canUseVnc`); `CuPermissionInline` only in local/desktop mode; browser sub-config; `KanbanConfigSection` when `kanban` enabled (0-board hint, multi-board picker, syncs `kanban_last_board_id`); `ExternalCliConfigSection` when `external_cli` enabled |
| `KanbanConfigSection.tsx` | Helper | Kanban chat target board: listBoards on mount, 0-board Settings link, Select when multiple boards without valid saved id; pairs with `messageRequest` send guard |
| `MediaCredentialInline.tsx` | Helper | Amber inline warning when image/video/tts enabled but provider credentials missing (links to Settings) |
| `OrgMarketplace.tsx` | Feature | Org marketplace browse/install grid + admin force-push button (sandbox-only) |
| `PublishToOrgButton.tsx` | Feature | One-click publish current agent to org marketplace (sandbox-only) |

## Built-in tools

Tool IDs are defined in `@/store/chat/types/builtinTools.ts` and must stay in sync with server `resolve_builtin_tool_flags()` in `profile_resolver.py` (`planning`, `answer_tool`, `render_ui`, `external_cli` → `enable_external_cli`, `cron` → `enable_cron_eager`, …).
