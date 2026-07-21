# Blender MCP Pitfalls

Detailed lessons learned, version-specific issues, and performance tips.

## Connection & Setup

### 1. Addon must be reconnected each Blender session

The BlenderMCP addon bridge disconnects when Blender restarts. Every new
Blender session: N-panel > BlenderMCP > Connect. "Connection refused" from
tools always means this step was missed.

### 2. Background mode is unsupported

The addon refuses to start under `blender -b`. For headless rendering on
servers: `xvfb-run blender` provides a virtual display. GPU rendering (CUDA/
OptiX/HIP) works fine under Xvfb.

### 3. Bridge timeout on large scripts

The MCP bridge has a timeout (typically 30–60s). Complex operations that take
longer will be killed. Split into multiple calls:
- Good: separate calls for mesh creation, material assignment, animation.
- Bad: one giant script that builds entire scene + renders.

### 4. Script execution returns empty in Blender 4.x

Blender 4.0+ changed some internal execution context. If `execute_blender_code`
returns empty/null but the operation succeeded (verify with `get_scene_info`),
this is a known bridge limitation — the execution worked, just the return
value reporting changed.

## bpy API Gotchas

### 5. ops require correct context

`bpy.ops.*` functions require specific context state:
- Most mesh ops need the object to be **active** AND in **Edit Mode**.
- `shade_smooth()` needs the object **selected** in **Object Mode**.
- `modifier_apply()` needs the object **active** in Object Mode.

Fix pattern:
```python
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode='OBJECT')
```

Prefer `bpy.data.*` direct manipulation when possible — it doesn't require
context setup.

### 6. Object naming collisions

Blender auto-suffixes duplicate names: "Cube" → "Cube.001" → "Cube.002".
Always assign unique names explicitly, or capture the reference immediately:

```python
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.active_object  # capture immediately
obj.name = "MyUniqueName"
```

Don't rely on `bpy.data.objects["Cube"]` after adding multiple cubes.

### 7. Material slot assignment

Materials are assigned to mesh data, not the object directly. Multiple objects
sharing mesh data share materials. For per-object materials:

```python
obj.data = obj.data.copy()  # make single-user
obj.data.materials.append(mat)
```

### 8. Euler rotation gimbal lock

For complex rotations, prefer quaternions or set rotation mode:

```python
obj.rotation_mode = 'QUATERNION'
obj.rotation_quaternion = (w, x, y, z)
```

Or use matrices for compound transforms:

```python
from mathutils import Matrix, Euler
mat_rot = Euler((x, y, z)).to_matrix().to_4x4()
obj.matrix_world = mat_rot
```

### 9. Collection visibility vs render visibility

Objects can be visible in viewport but hidden from render (or vice versa):
- `obj.hide_viewport` — viewport visibility
- `obj.hide_render` — render visibility
- Collection eye icon — viewport
- Collection camera icon — render

### 10. Proportional units

Blender uses meters by default. Common scale issues with imports:
- FBX from UE: arrives 100× too large (cm → m mismatch)
- STL files: often unitless, may need manual scaling

## Performance Tips

### 11. Reduce sample count for previews

Don't use 256+ samples for intermediate verification renders. Use 32–64
samples for quick checks, full samples only for final output.

### 12. Viewport shading for screenshots

`get_viewport_screenshot` captures whatever shading mode is active. For
material verification, ensure viewport is in Material Preview or Rendered mode:

```python
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        area.spaces[0].shading.type = 'MATERIAL'
        break
```

### 13. Large meshes: avoid high-poly in viewport

Subdivision Surface modifier: keep viewport levels low (1–2), render levels
higher (3–4). Only increase viewport levels for specific verification shots.

### 14. Clean up unused data

After many iterations, orphaned data blocks accumulate:

```python
bpy.ops.outliner.orphans_purge(do_recursive=True)
```

## Version-Specific Notes

### Blender 3.x → 4.x changes

- `bpy.context.scene.eevee` → `bpy.context.scene.eevee` (mostly same, but
  some properties renamed)
- EEVEE Next in 4.x: `scene.render.engine = 'BLENDER_EEVEE_NEXT'`
- Principled BSDF input names changed:
  - "Subsurface" → "Subsurface Weight"
  - "Transmission" → "Transmission Weight"
  - "Specular" → "Specular IOR Level"
  - "Coat" (new, was "Clearcoat" pre-4.0)
  - "Sheen" (new, was "Sheen Tint" pre-4.0)

### Blender 4.x specifics

- Geometry Nodes are preferred over older particle systems for new work.
- Asset Browser is the standard way to manage reusable assets.
- `bpy.ops.object.shade_smooth()` deprecated in favor of
  `bpy.ops.object.shade_smooth_by_angle()` (4.1+).
