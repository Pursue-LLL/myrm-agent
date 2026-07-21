# Tool Surface Reference

How Epic's editor-embedded MCP server organizes, advertises, and executes
tools, and how to extend the surface. Everything here is against UE 5.8's
experimental plugin (`ModelContextProtocol`); the live `describe_toolset` schema
always outranks this file.

## Architecture

The **Unreal MCP** plugin hosts an HTTP server inside the editor process
(default `http://127.0.0.1:8000/mcp`, loopback-only, no auth, HTTP + SSE).
It implements MCP but ships no tools. Tools come from **Toolsets** — classes
deriving from `UToolsetDefinition` (C++) or `unreal.ToolsetDefinition` (Python)
— collected by the **Toolset Registry** subsystem. The shipped tools live in
per-domain plugins; **AllToolsets** aggregates ~21 of them.

Execution is **serialized onto the game thread** — one tool call at a time,
editor UI blocked while each runs.

## Tool-Search Mode (Default)

With `Enable Tool Search` on (default), `tools/list` advertises exactly three
meta-tools:

| Meta-tool | Args | Returns |
|-----------|------|---------|
| `list_toolsets` | — | Registered toolset names + descriptions |
| `describe_toolset` | toolset name | JSON Schemas for every tool in that toolset |
| `call_tool` | toolset/tool name + arguments | Tool result |

Discipline:
- `list_toolsets` once per session; re-run only after `RefreshTools` or reconnect.
- `describe_toolset` before first use of any toolset.
- Results: primitive results wrapped as `{"result": ...}`.

## call_tool Dispatch Semantics

Critical details where naive clients fail:

- `list_toolsets` returns **fully-qualified** names (e.g.
  `editor_toolset.toolsets.scene.SceneTools`). Use verbatim.
- `tool_name` must be the **short** name (`get_current_level`, not dotted form).
- Args: `{"toolset_name": ..., "tool_name": ..., "arguments": {...}}`.
- **`TOptional` parameters must be passed as `null`** — omitting them errors.
- **Schema `required` is literal.** Pass `""` / `[]` for "any" semantics.
- **Property names are camelCase with UE's `b` prefix** (`bUseTemperature`).
- **Object references use `{"refPath": "<soft object path>"}`** everywhere.
- **`ObjectTools.set_properties` takes `values` as a JSON string**, not object.

## Shipped Toolsets (Core Surface)

The registry is project-dependent; `describe_toolset` is the source of truth.

**EditorToolset (Python toolsets):**

| Toolset | Key tools |
|---------|-----------|
| `scene.SceneTools` | `load_level`, `get_current_level`, `find_actors`, `add_to_scene_from_class`, `add_to_scene_from_asset`, `remove_from_scene`, `save_actor` |
| `actor.ActorTools` | labels, tags, transform get/set, parenting, components |
| `primitive.PrimitiveTools` | `add_cube`, `add_sphere`, `add_cylinder`, `add_cone` |
| `object.ObjectTools` | `list_properties`, `get/set_properties` (JSON string), `reset_properties` |
| `material_instance.MaterialInstanceTools` | create, list/get/set parameters |
| `asset.AssetTools` | find, load, save, delete, duplicate, import |
| `blueprint.BlueprintTools` | Blueprint authoring (DSL-based) |
| `programmatic.ProgrammaticToolset` | Batching escape hatch |

**EditorAppToolset (C++):** `CaptureViewport`, `CaptureEditorImage`,
camera get/set, selection, `StartPIE`/`StopPIE`, viewport screenshots.

**Other:** `LogsToolset`, `SemanticSearchToolset`, `NiagaraToolsets`,
`PCGToolset`, `AutomationTestToolset`, `ConfigSettingsToolset`,
`SequencerTools` (140 tools), and more — 67+ toolsets on a blank project.

## ProgrammaticToolset — Sanctioned Batching

For 5+ homogeneous operations in one round-trip:

1. `get_execution_environment` (mandatory first call) → returns instructions.
2. `execute_tool_script(script)` → sandboxed Python defining `run() -> dict`.
   Inside: `execute_tool(fully_qualified_tool_name, json_string)`.

Allowed imports: `json`, `math`, `datetime`, `copy`, `re`, `time`.
Scripts run in an editor transaction scope (undo-friendly).

## Plugin Configuration

Editor Preferences > General > Model Context Protocol:

| Property | Default | Notes |
|----------|---------|-------|
| Auto Start Server | `false` | Turn on for frictionless sessions |
| Server Port Number | `8000` | Change on conflict |
| Enable Tool Search | `true` | Keep on |

Console commands: `ModelContextProtocol.StartServer`, `.StopServer`,
`.RefreshTools`.

## Extending: Custom Toolsets

Python toolsets (recommended):

```python
import unreal
import toolset_registry

@unreal.uclass()
class MyTools(unreal.ToolsetDefinition):
    """Toolset description for the agent."""

    @toolset_registry.tool_call
    @staticmethod
    def my_operation(param: str) -> str:
        """Tool description.

        Args:
            param: Parameter description.

        Returns:
            Result description.
        """
        ...
```

After authoring: `ModelContextProtocol.RefreshTools`, then re-`list_toolsets`.
