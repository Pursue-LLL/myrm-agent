---
name: unreal-mcp
description: >-
  Drive Unreal Engine through Epic's editor-embedded MCP server — build scenes,
  place actors, author Blueprints, light cinematics, capture renders, and
  automate the editor from natural language. Covers tool-search discovery,
  serial game-thread discipline, scene-craft values, and verification workflow.
version: 1.0.0
category: creative
tags:
  - unreal
  - unreal-engine
  - ue5
  - 3d
  - mcp
  - scenes
  - cinematics
  - lighting
  - gamedev
requires: "Unreal Editor 5.8+ with Unreal MCP plugin enabled and server running"
allowed-tools: bash_code_execute_tool file_read_tool
contract:
  steps:
    - "Discover: list_toolsets → describe_toolset → understand available surface"
    - "Plan: extract brief, decide build order, post todo list"
    - "Build: one call at a time, serial on game thread, verify each milestone"
    - "Verify: screenshot + vision judgment against the brief"
    - "Save: save level + dirty packages after every milestone"
    - "Deliver: report actor labels, asset paths, capture file paths"
  potential_traps:
    - description: "Issuing overlapping MCP calls — game thread deadlocks"
      mitigation: "Strictly one call, await result, then next. Never batch mcp_* calls."
      severity: critical
    - description: "Spawning duplicate environment actors into template levels"
      mitigation: "Query existing actors first; configure what exists, spawn only what's missing"
      severity: high
    - description: "Using physical lux values in low-calibration template worlds"
      mitigation: "Read existing sun intensity first; work relative if it's single-digit"
      severity: high
    - description: "Guessing tool parameter names instead of reading schemas"
      mitigation: "Always describe_toolset before first use; schemas are the contract"
      severity: high
  verification_steps:
    - step_id: tools_discovered
      description: "Tool surface discovered via list_toolsets + describe_toolset"
      validation_method: "Can name the qualified toolset for the needed capability"
      is_required: true
    - step_id: scene_inspected
      description: "Existing scene state queried before any edits"
      validation_method: "Know what actors already exist, especially environment actors"
      is_required: true
    - step_id: visual_verified
      description: "Screenshot captured and judged after each milestone"
      validation_method: "Capture matches the brief; scale, lighting, composition correct"
      is_required: true
  success_criteria: "Scene matches the user's brief, visually verified, level saved"
  estimated_duration_seconds: 1800
---

# Unreal Engine MCP Skill

Companion skill for the `unreal-engine` integration in the Myrm catalog. The
MCP server (Epic's official, experimental "Unreal MCP" plugin) runs INSIDE the
Unreal Editor process and exposes editor functionality as typed tools. This
skill teaches how to drive it: discovering the live tool surface, sequencing
calls safely, translating natural-language asks into scenes that look good, and
verifying work visually.

## When to Use

Use when the user wants anything done in Unreal Engine: build or dress a level,
spawn/move/delete actors, set up lighting and atmosphere, create material
instances, frame a camera shot, capture screenshots or renders, import assets,
inspect the scene, run automation tests, or script the editor.

Don't use for: mesh modeling/sculpting (use `blender-mcp` and import the
result), or for editing Unreal C++ source (that's normal code work via the
terminal).

## Prerequisites

### Editor side (one-time)

1. Unreal Editor **5.8+** with a project open.
2. **Edit > Plugins** — enable **Unreal MCP** (Toolset Registry auto-enables).
   Restart when prompted.
3. Also enable **AllToolsets** — Unreal MCP ships NO tools itself; AllToolsets
   provides the shipped toolsets (SceneTools, ActorTools, etc.).
4. **Edit > Editor Preferences > Model Context Protocol** — enable **Auto Start
   Server**. Default: `http://127.0.0.1:8000/mcp`.

### Myrm side (one-time)

Connect via **Settings > Integrations > Unreal Engine** (catalog entry). The
connection probes the live server for reachability.

### Every session

1. Launch Unreal Editor, wait for project load; confirm server started (Output
   Log shows bind address).
2. Start a Myrm session. Tools register as `mcp_unreal_engine_*`.
3. Sanity check: call `mcp_unreal_engine_list_toolsets` and confirm toolsets
   appear.

## The Tool Surface: Discovery, Not a Fixed List

By default the plugin runs in **tool-search mode**: `tools/list` returns only
three meta-tools:

| Tool | Purpose |
|------|---------|
| `mcp_unreal_engine_list_toolsets` | Names + descriptions of registered toolsets |
| `mcp_unreal_engine_describe_toolset` | Full JSON schemas for one toolset's tools |
| `mcp_unreal_engine_call_tool` | Invoke a tool with arguments, get result |

The discovery walk, always in this order:

1. `list_toolsets` → see what capability groups the project has (surface is
   project-dependent). Names are **fully qualified** — use verbatim.
2. `describe_toolset` on the group you need → read parameter schemas. Never
   guess parameter names.
3. `call_tool` with qualified toolset name, SHORT tool name, and schema-matching
   arguments.

Cache what you learn for the session; re-list only after editor-side changes.

## Operating Loop

Every Unreal task follows this loop:

1. **Inspect first.** List toolsets, query scene state before touching anything.
   Never assume an empty or default level.
2. **Act in small, single-purpose calls.** One logical step per `call_tool`.
   Execution is serial on the game thread — big operations freeze the editor.
3. **NEVER issue overlapping calls.** Do not batch multiple `mcp_unreal_engine_*`
   calls in one turn. Strictly: one call → await result → next call. This
   overrides general parallel-tool guidance.
4. **Read every result.** Many tools report success/failure in the response body
   without protocol-level exceptions. Anything not explicit success = diagnose.
5. **Verify visually.** After each milestone, capture a viewport screenshot and
   judge it against the brief (composition, exposure, scale).
6. **Save often.** Editor edits are in-memory until saved; a crash loses
   everything. Save before AND after bulk changes, and after every milestone.
7. **Report concretely.** Actor labels, asset paths (`/Game/...`), capture file
   locations.

## Physical World Rules

- Units: **centimeters**. Axes: **Z-up**, X-forward. Rotations: degrees.
- Human eye height ≈ 165 cm; door ≈ 210×90 cm.
- Content paths: `/Game/Folder/Asset.Asset` (project), `/Engine/...` (engine).
- Actor **labels** (Outliner display) ≠ actor **names** (internal, unique).
  Prefer resolving by label/class queries, then hold whatever handle is returned.
- Prefer physical lighting values (lux/candela/Kelvin) — but FIRST read the
  existing sun's intensity to learn the calibration convention.

## From Natural Language to a Scene

1. **Extract the brief.** Subject, mood, time of day, style, deliverable.
2. **Plan build order.** Environment shell → blocking → lighting → materials →
   detail → camera → capture.
3. **Build with the loop above**, one milestone at a time, screenshot at each.
4. **Art-direct yourself.** Compare each screenshot against the brief.
5. **Deliver.** Captures as file paths, plus a summary of what exists.

## Reference Files

Load on demand; keep SKILL.md-level rules in mind throughout.

| Reference | Contents |
|-----------|----------|
| `references/tool-surface.md` | Shipped toolsets catalog, call_tool dispatch semantics, custom toolset authoring, plugin configuration |
| `references/advanced-workflows.md` | ProgrammaticToolset batching, Blueprint DSL loop, PIE testing, Sequencer, LogsToolset debugging |
| `references/scene-craft.md` | Physical light values, color temperatures, exposure, fog, mood recipes, camera/framing, scale tables |
| `references/recipes.md` | End-to-end worked builds with exact call sequences and values |
| `references/pitfalls.md` | Setup, calling discipline, editor state, content, and delivery pitfalls with fixes |

## Top Pitfalls (full list in references/pitfalls.md)

- **Start order matters.** Editor + server first, then Myrm session. Missing
  tools = wrong order.
- **One call at a time.** Parallel calls against the game thread deadlock.
- **Query before spawning.** Template levels already have environment actors;
  duplicates cause whiteouts.
- **Schema is contract.** Never guess param names; describe_toolset first.
- **Save per milestone.** Unsaved edits die on crash.
- **TOptional params must be explicit null.** Omitting them errors.
- **Property names are PascalCase with UE `b` prefix.** Writing wrong case
  silently no-ops.
