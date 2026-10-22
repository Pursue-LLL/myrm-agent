# src/components/channels/pairing/

## Overview

Model-agnostic external channel token binding and visual pairing wizard components.
Decouples channel setup completely from LLM chat loops, offering dynamic QR code rendering, webhook callback handshake confirmation, and one-click ping connectivity self-checks.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `index.ts` | Facade | Module exports for pairing types, service, modal, and health check card | ✅ |
| `channelPairingTypes.ts` | Types | TypeScript data contracts with strict zero-any types | ✅ |
| `channelPairingService.ts` | Service | Client REST communication, session polling, and offline mock fallbacks | ✅ |
| `ChannelHealthCheckCard.tsx` | Component | One-click ping connectivity probe and latency indicator card | ✅ |
| `ChannelPairingWizardModal.tsx` | Component | 4-step wizard modal covering platform select, dynamic QR, token bind, and ping check | ✅ |

## Dependencies

- Lucide React icons
- `react-i18next` for localization
- Backend API at `/api/channels/pairing`
