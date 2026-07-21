# Advanced Workflows

Everything here was verified against a running UE 5.8 editor.

## ProgrammaticToolset — Batching Without Breaking Serial

`editor_toolset.toolsets.programmatic.ProgrammaticToolset` allows N operations
in one MCP round-trip while preserving the serial-call rule.

1. Call `get_execution_environment` ONCE per session first. Returns allowed
   modules and usage instructions.
2. `execute_tool_script` takes `{"script": "<python>"}`. Script must define
   `run() -> Dict[str, Any]`.
3. Inside: `execute_tool(fully_qualified_name, json_string)` calls any tool.
   Tool name is FULLY QUALIFIED INCLUDING tool segment.
4. `execute_tool` returns dict-like; unwrap with `["returnValue"]`.
5. Allowed imports: `json`, `math`, `datetime`, `copy`, `re`, `time` only.
6. Return value comes back as JSON in `returnValue`.

Example (12-column colonnade, ONE round-trip):

```python
import json, math

def add_cylinder(actor_ref, name, radius, height, x, y, z):
    return execute_tool(
        "editor_toolset.toolsets.primitive.PrimitiveTools.add_cylinder",
        json.dumps({"actor": actor_ref, "name": name, "radius": radius,
                    "height": height,
                    "local_transform": {"location": {"x": x, "y": y, "z": z}}}))

def run():
    spawn = execute_tool(
        "editor_toolset.toolsets.scene.SceneTools.add_to_scene_from_class",
        json.dumps({"actor_type": {"refPath": "/Script/Engine.Actor"},
                    "name": "Colonnade",
                    "xform": {"location": {"x": 0, "y": 0, "z": 0}}}))
    host = spawn["returnValue"]
    n, ring_r = 12, 900.0
    for i in range(n):
        a = 2.0 * math.pi * i / n
        add_cylinder(host, "Shaft_%02d" % i, 40, 360,
                     ring_r * math.cos(a), ring_r * math.sin(a), 210)
    return {"colonnade": host["refPath"], "columns": n}
```

Use when: 5+ homogeneous ops. Don't use when: you need intermediate results.

## Blueprint Authoring — DSL Loop

`BlueprintTools` (53 tools) authors real Blueprints via s-expression DSL:

1. `create` → returns Blueprint refPath.
2. `list_graphs` → graph refPaths.
3. `get_graph_dsl_docs` → grammar documentation (read before writing).
4. **Resolve EVERY node ID with `find_node_types`** — node IDs must match the
   live registry exactly. Common gotchas:
   - Engine events: `EventTick`, `EventBeginPlay` (not `(event Tick)`).
   - Math: `Math|Rotator|MakeRotator` (not bare `MakeRotator`).
   - No `(self)` node — omit `:self` for owning actor calls.
5. `write_graph_dsl` → returns null on success; error names failing node.
6. `compile_blueprint` → verify clean.
7. Spawn instance via `SceneTools.add_to_scene_from_asset`.

## PIE Sessions

`EditorAppToolset.StartPIE` options:
- `bSimulate` (required): true = Simulate-In-Editor.
- `playMode` (required): `PlayMode_InViewPort` recommended.
- `warmupSeconds` (required): settle time after PostPIEStarted.

Test loop: compile → StartPIE → sample state → StopPIE → judge.

## Sequencer (140 tools)

`SequencerTools` follows open-sequence-implicit-target model. Key capabilities:
- **Structure**: `add_actors`, `add_spawnable_from_class`, `create_camera`.
- **Tracks/sections**: `add_track_to_binding`, `add_section`, range/blend.
- **Transport**: `play`, `pause`, `play_to`, `set_playhead_frame`.
- **Keyframing**: sibling `SequencerKeyframingTools` (22 tools).

## LogsToolset — Self-Debugging

`GetLogCategories`, `Get/SetVerbosity`, `GetLogEntries`. After failures, pull
recent logs filtered to relevant category (`LogBlueprint`, `LogNiagara`, etc.).

## Decision Table

| Situation | Reach for |
|-----------|-----------|
| 5+ homogeneous ops | ProgrammaticToolset script |
| Gameplay behavior | BlueprintTools DSL loop |
| Camera animation | SequencerTools + KeyframingTools |
| Runtime testing | StartPIE (simulate) |
| Find assets | SemanticSearch, then AssetTools |
| Something failed silently | LogsToolset GetLogEntries |
| Project has agent skills | AgentSkillToolset first |
