# agent-avatar

Agent Avatar Generation and Dice Lock Widget.

## Overview
Provides a visual deterministic SVG avatar generation and Dice Lock widget system:
1. Deterministic SVG Generator: Zero-network client-side SVG generation based on seed hash algorithms across 4 styles (`beam`, `pixel`, `cyberpunk`, `bauhaus`).
2. Interactive Dice Lock: Protects custom-tailored avatars from accidental overwriting while allowing randomized dice rolls when unlocked.
3. Color & Style Palette: 8-color circular palette and instant style presets.
4. AI Generative Avatar Studio: Dual-tab modal supporting text prompt AI rendering with fallback mechanisms.

## File Structure

| File | Status | Description |
| --- | --- | --- |
| `avatarTypes.ts` | Core | Pure domain types for avatar styles, color presets, metadata, and API payloads. |
| `avatarGenerator.ts` | Algorithm | Deterministic zero-network SVG markup generator with seed hash mapping. |
| `avatarService.ts` | Service | Client-side API service with offline deterministic fallbacks and DiceBear proxy. |
| `DiceRollButton.tsx` | Component | Interactive button triggering seed randomization with 3D rolling animation and lock guard. |
| `AvatarLockWidget.tsx` | Component | Compact avatar preview with floating lock badge, style pills, and color palette. |
| `AvatarGeneratorModal.tsx` | Modal | Dual-mode studio dialog offering deterministic dice roll and AI generative prompt workflows. |
| `index.ts` | Export | Public entry barrel exporting all avatar types, algorithms, services, and components. |
