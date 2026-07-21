# Pitfalls & Lessons

Read before your first session; return whenever something misbehaves. Ordered
by when they bite: setup → calling discipline → editor state → content →
delivery.

## Setup & Connection

### 1. Start order: editor first, Myrm session second

MCP tools are probed at session start. If the editor isn't up yet, no tools
exist. Fix: launch editor, confirm server bound (Output Log), then start a new
session.

### 2. Server enabled but no tools advertised

Unreal MCP ships the SERVER, not tools. If `list_toolsets` returns nothing, the
AllToolsets plugin isn't enabled. Fix: Edit > Plugins, restart editor and
session.

### 3. macOS: full Xcode required

The editor needs Xcode for Metal shaders. Without it, first launch dies.
Install full Xcode, open once to accept license, verify with `xcode-select -p`.

### 4. Port 8000 conflicts

Common collisions: dev servers, Jupyter. Change Server Port Number in Editor
Preferences AND the integration URL. Verify with
`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/mcp`.

### 4b. "Connection refused" mid-session

Editor was closed or crashed. Don't retry in a loop — ask user to relaunch,
then reconnect with a new session.

## Calling Discipline

### 5. One call at a time — never batch

Serial game-thread execution. Batching `mcp_unreal_engine_*` calls in one turn
IS overlapping calls → deadlock. Strictly sequential.

### 6. Editor freezes during every call

Game-thread execution blocks the editor UI. Keep calls small. Split bulk
operations (e.g. "spawn 200 trees") into chunks.

### 7. Modal dialogs deadlock

Anything popping a modal blocks your call. If a call hangs, ask user to check
for dialogs. Prefer tool paths that avoid interactive prompts.

### 8. Timeouts

Default per-call timeout may be exceeded by imports, shader compiles, renders.
After any timeout, RE-QUERY state before retrying — the operation may have
completed (duplicate actors are the classic case).

### 9. Stale schemas after editor changes

After enabling plugins or authoring toolsets: `ModelContextProtocol.RefreshTools`,
then re-list/re-describe. New C++ UFUNCTIONs need full editor restart.

### 9b. Error schema is the tiebreaker

Some tools take refPath objects, others take plain strings. When a call fails,
the error text contains the complete input schema — read it first.

## Editor & Scene State

### 10. Never assume a fresh level

Template levels ALREADY contain environment actors. Duplicates compound (double
fog = whiteout). Rule: `find_actors` for each environment class FIRST; configure
existing; spawn only missing.

### 10b. Read existing sun before imposing physical values

Template sun may be `intensity: 10`, not physical lux. Setting 12,000 lux into
that world blows to white. Read first; work RELATIVE if calibrated low.

### 11. In-memory edits lost on crash

Save level + dirty packages after every milestone. Untitled levels may route
through Save-As dialog (deadlock risk).

### 12. Label ≠ Name ≠ Path

Labels (Outliner) are settable but non-unique. Names are auto-generated. Full
object path is the stable identifier. When you create an actor, set a label
immediately and record the returned handle.

### 12b. Property writes can silently no-op

PascalCase at reflection layer; wrong case silently changes nothing. After
writes, READ BACK the value and compare.

### 13. Play In Editor changes the world

Queries during PIE may target the transient PIE world; edits evaporate when
play stops. Do edit work outside PIE.

## Content & Assets

### 14. Long package names, not file paths

Assets: `/Game/Folder/Asset.Asset`. Windows paths are wrong everywhere except
import/export file arguments.

### 15. Referenced ≠ loaded

Project assets may need loading; typo'd paths fail soft (empty mesh). After
assigning, re-query to confirm.

### 16. Material edits: instances, not parents

Editing parent Material recompiles shaders globally. Create Material Instances,
set parameters. Parameter names must match parent's exposed parameters exactly.

### 16b. Emissive needs intensity > 1 to bloom

Emissive ≤1.0 is self-lit but never blooms. 3–10 gives visible glow.

### 16c. Shader compilation is async

Screenshots taken mid-compile show old/checkerboard state. Wait for compilation
before judging visuals.

## Delivery

### 17. Screenshot judgment is part of the job

Capture the viewport, judge against the brief (exposure, composition, scale).
Don't declare done from numbers alone.

### 17b. Editor sprite icons appear in captures

Hide Billboard/Sprite/Arrow components with `bVisible: false` via
`ObjectTools.set_properties`. Don't try post-processing removal.

### 17c. Viewport axis gizmo survives bShowUI=false

Plan spare margin and crop in post for hero deliverables.

### 18. Report package paths + file paths

User needs: actor labels + `/Game/...` paths, level save location, and absolute
filesystem paths of captures.
