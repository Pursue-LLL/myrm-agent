# Git Worktree & Session Checkout Anchor Subsystem Architecture

## Overview
Provides a sidebar multi-worktree switcher, session-to-checkout anchoring with mismatch detection, and a touched-files inspection view (addressing pi-web & Ajit worktree lessons).

## Components & Files
| File | Role | Primary Consumers |
|---|---|---|
| `worktreeTypes.ts` | Domain types for worktrees, anchors & touched files | Internal & UI consumers |
| `worktreeService.ts` | Client API layer with safe offline fallback | `useWorktreeStore.ts` |
| `useWorktreeStore.ts` | Zustand store managing worktree list, active pointer & anchor synchronization | Dropdown & Banner |
| `GitWorktreeDropdown.tsx` | Compact sidebar dropdown for switching & creating worktrees | Sidebar layout (`ChatSidebarContent`) |
| `SessionCheckoutAnchorBanner.tsx` | Smart anchor banner alerting worktree drift on session load | Chat window & session detail |
| `SessionTouchedFilesPopover.tsx` | Modal popover listing touched/modified files during session | `SessionCheckoutAnchorBanner` |
| `index.ts` | Module export facade | External components |
