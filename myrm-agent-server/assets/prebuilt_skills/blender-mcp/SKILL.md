---
name: blender-mcp
description: >-
  Drive Blender via the blender MCP server — create meshes, materials,
  animations, lighting setups, and renders through bpy Python. Covers the
  four-tool interface, common bpy patterns, verification workflow, and pitfalls.
version: 1.0.0
category: creative
tags:
  - blender
  - 3d
  - animation
  - modeling
  - bpy
  - mcp
  - rendering
requires: "Blender 3.0+ desktop instance with blender-mcp addon connected"
allowed-tools: bash_code_execute_tool file_read_tool
contract:
  steps:
    - "Inspect: get_scene_info before any modifications"
    - "Build: execute_blender_code in small focused calls (one logical step each)"
    - "Verify: get_viewport_screenshot between major steps"
    - "Render: output to absolute path and report location"
  potential_traps:
    - description: "Large monolithic scripts hitting bridge timeout"
      mitigation: "Break complex scenes into multiple smaller execute_blender_code calls"
      severity: high
    - description: "Relative render paths resolving on wrong filesystem"
      mitigation: "Always use absolute paths for render output"
      severity: medium
    - description: "Running Blender in background mode without display"
      mitigation: "Use xvfb-run for headless; addon refuses blender -b"
      severity: medium
  verification_steps:
    - step_id: scene_inspected
      description: "Current scene state known before modifications"
      validation_method: "get_scene_info returns expected object list"
      is_required: true
    - step_id: visual_verified
      description: "Viewport screenshot confirms intended result"
      validation_method: "get_viewport_screenshot shows correct objects/lighting"
      is_required: true
    - step_id: render_confirmed
      description: "Render file exists at reported path"
      validation_method: "Absolute path reported to user after render"
      is_required: true
  success_criteria: "Scene matches user intent, visually verified, render delivered"
  estimated_duration_seconds: 900
---

# Blender MCP Skill

Companion skill for the `blender` integration in the Myrm catalog. The MCP
server provides the connection to a running Blender instance; this skill teaches
the bpy idioms and pitfalls for driving it well. Everything goes through MCP
tools against a live Blender session.

## When to Use

Use when the user wants to create or modify anything in a running Blender
instance: meshes, materials, animations, lighting, renders. Also for modeling
assets destined for Unreal Engine (model here, import there).

Don't use for: Blender UI workflows (this is code-only via MCP), or for
operations better done directly in UE (use `unreal-mcp` instead).

## Prerequisites

### One-time setup

1. Connect via **Settings > Integrations > Blender** (catalog entry).
2. Install the addon inside Blender:
   - Download the addon from the blender-mcp repository.
   - Blender > Edit > Preferences > Add-ons > Install > select addon, enable
     "Interface: Blender MCP".

### Every session

1. Start Blender FIRST.
2. Press N in the viewport, open "BlenderMCP" tab, click "Connect".
3. Start the Myrm session. Tools register as `mcp_blender_*`.

The addon refuses `blender -b` (background mode). On headless machines, use
`xvfb-run blender` for a virtual display. GPU rendering works under Xvfb.

## Tool Surface

Four tools compose the entire interface:

| Tool | Purpose |
|------|---------|
| `mcp_blender_get_scene_info` | List objects before touching the scene |
| `mcp_blender_get_object_info` | Inspect one object (transform, materials) |
| `mcp_blender_get_viewport_screenshot` | Visual check of what you built |
| `mcp_blender_execute_blender_code` | Everything else — arbitrary bpy Python |

## Operating Procedure

1. **Call `get_scene_info` first** — never assume the scene is empty.
2. **Build with `execute_blender_code`** in small focused calls. One logical
   step per call: add objects, then materials, then animation. Large monolithic
   scripts hit the bridge timeout.
3. **Verify visually** with `get_viewport_screenshot` between major steps.
4. **Render** to an absolute path and report the file location to the user.

## Common bpy Patterns

### Clear scene

```python
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
```

### Add mesh objects

```python
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 0))
bpy.ops.mesh.primitive_cube_add(size=2, location=(3, 0, 0))
bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=2, location=(-3, 0, 0))
bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, -1))
```

### Create and assign material

```python
mat = bpy.data.materials.new(name="MyMat")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.8, 0.2, 0.1, 1.0)
bsdf.inputs["Roughness"].default_value = 0.3
bsdf.inputs["Metallic"].default_value = 0.0
obj = bpy.context.active_object
obj.data.materials.append(mat)
```

### Keyframe animation

```python
obj = bpy.data.objects["Cube"]
obj.location = (0, 0, 0)
obj.keyframe_insert(data_path="location", frame=1)
obj.location = (0, 0, 3)
obj.keyframe_insert(data_path="location", frame=60)
```

### Camera setup

```python
bpy.ops.object.camera_add(location=(7, -7, 5))
cam = bpy.context.active_object
cam.rotation_euler = (1.1, 0, 0.78)
bpy.context.scene.camera = cam
```

### Lighting

```python
bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
sun = bpy.context.active_object
sun.data.energy = 3.0
sun.data.color = (1.0, 0.95, 0.9)

bpy.ops.object.light_add(type='POINT', location=(-3, 2, 4))
point = bpy.context.active_object
point.data.energy = 100
point.data.color = (0.8, 0.9, 1.0)
```

### HDRI environment

```python
world = bpy.context.scene.world
world.use_nodes = True
nodes = world.node_tree.nodes
links = world.node_tree.links
nodes.clear()
bg = nodes.new('ShaderNodeBackground')
env = nodes.new('ShaderNodeTexEnvironment')
env.image = bpy.data.images.load("/path/to/hdri.hdr")
output = nodes.new('ShaderNodeOutputWorld')
links.new(env.outputs['Color'], bg.inputs['Color'])
links.new(bg.outputs['Background'], output.inputs['Surface'])
```

### Render to file

```python
scene = bpy.context.scene
scene.render.filepath = "/tmp/render.png"
scene.render.engine = 'CYCLES'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.cycles.samples = 128
bpy.ops.render.render(write_still=True)
```

### Modifiers

```python
obj = bpy.context.active_object
mod = obj.modifiers.new(name="Subsurf", type='SUBSURF')
mod.levels = 2
mod.render_levels = 3

mod = obj.modifiers.new(name="Solidify", type='SOLIDIFY')
mod.thickness = 0.05
```

### Export for Unreal

```python
bpy.ops.export_scene.fbx(
    filepath="/tmp/model.fbx",
    use_selection=True,
    apply_scale_options='FBX_SCALE_ALL',
    axis_forward='-Y',
    axis_up='Z'
)
```

## Pitfalls

- **Bridge must be connected each session.** "Connection refused" = Blender not
  running or addon not connected. Fix that, don't retry.
- **Break scripts into small calls.** Large scripts hit bridge timeout. One
  logical step per call.
- **Absolute render paths only.** `/tmp/render.png`, not `./render.png` —
  paths resolve on the BLENDER host's filesystem.
- **`shade_smooth()` requires selection.** Object must be selected and in
  object mode.
- **`execute_blender_code` is unsandboxed.** Same trust level as terminal.
  Don't paste untrusted code.
- **Blender version differences.** API names change between versions (e.g.
  `bpy.context.view_layer.objects.active` vs older patterns). Check version
  if operations fail.
- **ops vs data API.** `bpy.ops.*` requires correct context (mode, selection).
  When possible, prefer `bpy.data.*` direct manipulation for reliability.

## Verification

- `get_scene_info` returns expected object list after each build step.
- `get_viewport_screenshot` shows the scene you intended.
- After render, confirm output file exists and report its absolute path.

## Reference Files

| Reference | Contents |
|-----------|----------|
| `references/bpy-patterns.md` | Advanced bpy operations: procedural modeling, node materials, modifiers, physics, particles |
| `references/pitfalls.md` | Detailed version-specific issues, ops context requirements, performance tips |
