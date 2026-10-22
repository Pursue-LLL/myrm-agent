# components/features/runtime/

## Overview

Pure functional multi-surface run state projection and Attempt telemetry drawer components.
Implements MateClaw parity (`UI = Project(RunState, Events)`), providing seamless switching between Chat View, Runtime Console, Deliverables Board, and Audit Ledger without losing state across view transitions.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `index.ts` | Facade | Public exports for runtime projection contracts, hooks, and drawer components | ✅ |
| `runtimeProjectionTypes.ts` | Schema | TypeScript contracts for run snapshot, attempts, deliverables, and audit entries | ✅ |
| `runtimeProjectionService.ts` | Service | Client communication layer for /api/v1/runs with resilient fallbacks | ✅ |
| `useRunProjection.ts` | Hook | Pure functional hook managing monotonic state aggregation and optimistic surface switching | ✅ |
| `QuadSurfaceSwitcher.tsx` | Component | Four-way projection surface switcher bar (Chat, Runtime Console, Deliverables, Audit) | ✅ |
| `AttemptWaterfallInspector.tsx` | Component | Attempt waterfall timeline, token rate watermark, and fault diagnostic viewer | ✅ |
| `RuntimeConsoleDrawer.tsx` | Component | Main runtime console drawer integrating multi-surface projections with zero emojis | ✅ |

## Dependencies

- `lucide-react`: Icons (`Terminal`, `MessageSquare`, `PackageCheck`, `ShieldAlert`, `CheckCircle2`, `XCircle`, `Zap`, `Clock`, `Lock`, `Shield`)
- `next-intl`: Internationalization strings
