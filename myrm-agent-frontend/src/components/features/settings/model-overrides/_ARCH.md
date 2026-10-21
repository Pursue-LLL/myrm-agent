# src/components/features/settings/model-overrides/

## Overview

User-defined model context window and pricing override settings panel.
Implements Hermes Agent v0.21.0 model_overrides parity, offering dynamic context window sliders, output token limit customization, and a live BYOK token economics calculator.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `index.ts` | Facade | Module exports for types, service, dialog, and BYOK calculator | ✅ |
| `modelOverridesTypes.ts` | Types | TypeScript data contracts with strict zero-any types | ✅ |
| `modelOverridesService.ts` | Service | Client REST communication, preloaded 2026 SKU lookups, and offline calculation fallbacks | ✅ |
| `ByokCostCalculatorCard.tsx` | Component | Live BYOK token economics and run cost estimation card | ✅ |
| `ModelOverridesDialog.tsx` | Component | Interactive modal dialog with slider, SKU template cloner, and overrides list | ✅ |

## Dependencies

- Lucide React icons
- `next-intl` for localization
- Backend API at `/api/settings/model-overrides`
