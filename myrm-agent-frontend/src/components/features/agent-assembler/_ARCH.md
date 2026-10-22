# agent-assembler

Visual Modular Agent Assembler and Block-Based Capability Composer.

## Overview
Provides a visual Lego-style 3-pane workbench for autonomous agent assembly:
1. Left Pane: Capability Blocks Pool across 6 dimensions (Brain, Persona, Tools, Skills, Memory, Sandbox).
2. Middle Pane: Interactive Assembly Canvas with real-time dependency health check banner and token estimator.
3. Right Pane: In-situ Sandbox Testbed & Dry-run execution runner.

## File Structure

| File | Status | Description |
| --- | --- | --- |
| `assemblerTypes.ts` | Core | Pure domain types for capability blocks, blueprints, validation results, and dry-run responses. |
| `assemblerService.ts` | Service | Client-side API integration with offline fallback validation and sandbox simulation. |
| `CapabilityBlockCard.tsx` | Component | Individual capability block card with category styling, toggle switch, removal, and parameter drawer. |
| `AssemblerBlockCatalog.tsx` | Component | Category-filtered and searchable catalog tray of available building blocks. |
| `AssemblerCanvas.tsx` | Component | Assembly canvas displaying equipped blocks and real-time dependency status banner. |
| `AssemblerDryRunPlayground.tsx` | Component | Testbed playground executing single-turn simulated dry-runs and displaying predicted tools. |
| `AgentVisualComposer.tsx` | Facade | Top-level 3-pane composer coordinating state, starter presets, JSON export, and save actions. |
| `index.ts` | Export | Public entry barrel for all agent-assembler components and types. |
