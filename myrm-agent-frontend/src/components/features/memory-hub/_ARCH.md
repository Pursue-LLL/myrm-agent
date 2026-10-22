# memory-hub

Agent Memory Asset Equipment Hub and Granular ACL Panel.

## Overview
Provides a comprehensive cognitive asset catalog and game-like equipment loadout system:
1. Four-Tier Asset Catalog: Organizes memory assets into `chat_memory`, `skill`, `wiki`, and `code_graph`.
2. Granular ACL Panel: Enforces `private`, `team`, and `project` isolation policies and explicit agent access lists.
3. Game-Like Equipment Slots: 4 visual slots for mounting active memory assets into the agent's cognitive loop with 1-click equip and unequip.
4. Resilient Service Client: Endpoints with offline deterministic fallbacks.

## File Structure

| File | Status | Description |
| --- | --- | --- |
| `memoryHubTypes.ts` | Core | Pure domain types for 4-tier assets, ACL scopes, equipment slots, and API contracts. |
| `memoryHubService.ts` | Service | Client REST API service with resilient offline fallback mocking. |
| `MemoryAssetCard.tsx` | Component | Cognitive asset card showing tier badge, ACL status capsule, preview snippet, and equip CTA. |
| `AgentEquipmentSlots.tsx` | Component | Visual 4-slot loadout rack displaying equipped assets, capacity counter, and unequip action. |
| `AssetAclDrawer.tsx` | Drawer | Granular ACL modal drawer allowing switching between Private, Team, and Project scopes. |
| `MemoryAssetHub.tsx` | Facade | Top-level dashboard coordinating search, tier filtering, ACL filtering, and equipment deck. |
| `index.ts` | Export | Public entry barrel for all memory-hub components, services, and types. |
