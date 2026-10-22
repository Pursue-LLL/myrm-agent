# components/features/commands/palette/

## Overview

Global fuzzy command palette (Cmd+K / Ctrl+K), rotating task placeholder engine, and live performance telemetry status bar suite.
Implements Hermes Agent v0.21.0 CLI/GUI parity & OpenHuman unified search hub parity, merging Actions/Controls with Thread/Message search under debounced and stale-cancelled query processing.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `index.ts` | Facade | Public exports for command palette types, hooks, and React components | ✅ |
| `globalCommandPaletteTypes.ts` | Schema | TypeScript contracts for actions, history items, telemetry metrics, and placeholders | ✅ |
| `useRotatingPlaceholder.ts` | Hook | Rotating goal-oriented placeholder engine reducing cold-start friction | ✅ |
| `LivePerformanceStatusBar.tsx` | Component | Live telemetry status bar with Cache Hit %, TTFT, Tokens/sec, and Global E-Stop | ✅ |
| `GlobalFuzzyCommandPalette.tsx` | Component | Unified Cmd+K search hub combining Actions and Thread History with zero emojis | ✅ |

## Dependencies

- `lucide-react`: Icons (`Command`, `Search`, `Bot`, `Sparkles`, `Download`, `OctagonAlert`, `MessageSquare`, `Clock`, `Database`, `Zap`, `Activity`)
- `next-intl`: Internationalization strings
