# Advanced bpy Patterns

Beyond the basics in SKILL.md — procedural modeling, node-based materials,
physics, particles, and workflow patterns for complex scenes.

## Procedural Modeling

### Boolean operations

```python
obj_a = bpy.data.objects["Base"]
obj_b = bpy.data.objects["Cutter"]
mod = obj_a.modifiers.new(name="Boolean", type='BOOLEAN')
mod.operation = 'DIFFERENCE'
mod.object = obj_b
bpy.context.view_layer.objects.active = obj_a
bpy.ops.object.modifier_apply(modifier="Boolean")
bpy.data.objects.remove(obj_b)
```

### Geometry from vertices

```python
import bmesh

mesh = bpy.data.meshes.new("CustomMesh")
obj = bpy.data.objects.new("CustomObject", mesh)
bpy.context.collection.objects.link(obj)

bm = bmesh.new()
v1 = bm.verts.new((0, 0, 0))
v2 = bm.verts.new((1, 0, 0))
v3 = bm.verts.new((0.5, 1, 0))
bm.faces.new((v1, v2, v3))
bm.to_mesh(mesh)
bm.free()
```

### Array + Curve deform (chain/rope pattern)

```python
bpy.ops.mesh.primitive_torus_add(major_radius=0.5, minor_radius=0.1)
link = bpy.context.active_object

mod = link.modifiers.new("Array", 'ARRAY')
mod.count = 20
mod.relative_offset_displace = (1.1, 0, 0)

bpy.ops.curve.primitive_bezier_curve_add()
curve = bpy.context.active_object
mod2 = link.modifiers.new("Curve", 'CURVE')
mod2.object = curve
```

### Displacement with texture

```python
bpy.ops.mesh.primitive_plane_add(size=10)
plane = bpy.context.active_object
bpy.ops.object.modifier_add(type='SUBSURF')
plane.modifiers["Subdivision"].levels = 6

mod = plane.modifiers.new("Displace", 'DISPLACE')
tex = bpy.data.textures.new("DispTex", type='CLOUDS')
tex.noise_scale = 1.5
mod.texture = tex
mod.strength = 0.5
```

## Node-Based Materials

### Glass/transparent

```python
mat = bpy.data.materials.new("Glass")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
bsdf.inputs["Transmission Weight"].default_value = 1.0
bsdf.inputs["Roughness"].default_value = 0.0
bsdf.inputs["IOR"].default_value = 1.45
mat.blend_method = 'HASHED'  # EEVEE transparency
```

### Emission/glow

```python
mat = bpy.data.materials.new("Glow")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
bsdf.inputs["Emission Color"].default_value = (0.0, 0.5, 1.0, 1.0)
bsdf.inputs["Emission Strength"].default_value = 5.0
```

### Procedural texture (noise-based)

```python
mat = bpy.data.materials.new("Procedural")
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links

noise = nodes.new('ShaderNodeTexNoise')
noise.inputs['Scale'].default_value = 5.0
noise.inputs['Detail'].default_value = 8.0

ramp = nodes.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].color = (0.1, 0.05, 0.02, 1)
ramp.color_ramp.elements[1].color = (0.6, 0.4, 0.2, 1)

bsdf = nodes.get("Principled BSDF")
links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
```

## Physics & Particles

### Rigid body simulation

```python
obj = bpy.data.objects["Cube"]
bpy.context.view_layer.objects.active = obj
bpy.ops.rigidbody.object_add(type='ACTIVE')
obj.rigid_body.mass = 5.0

ground = bpy.data.objects["Ground"]
bpy.context.view_layer.objects.active = ground
bpy.ops.rigidbody.object_add(type='PASSIVE')
```

### Particle system (rain/snow)

```python
obj = bpy.data.objects["Emitter"]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.particle_system_add()
ps = obj.particle_systems[0].settings
ps.count = 1000
ps.lifetime = 50
ps.emit_from = 'FACE'
ps.physics_type = 'NEWTON'
ps.normal_factor = -5.0  # downward
```

## Turntable Animation

```python
bpy.ops.object.empty_add(location=(0, 0, 0))
pivot = bpy.context.active_object
pivot.name = "TurntablePivot"

cam = bpy.data.objects["Camera"]
cam.parent = pivot
cam.location = (7, 0, 3)
cam.rotation_euler = (1.2, 0, 1.57)

pivot.rotation_euler = (0, 0, 0)
pivot.keyframe_insert(data_path="rotation_euler", frame=1)
pivot.rotation_euler = (0, 0, 6.283)
pivot.keyframe_insert(data_path="rotation_euler", frame=120)

for fc in pivot.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'
```

## Render Settings

### Cycles (quality)

```python
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = 256
scene.cycles.use_denoising = True
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.film_transparent = True  # transparent background
```

### EEVEE (fast preview)

```python
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.eevee.taa_render_samples = 64
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
```

## Collection Management

```python
col = bpy.data.collections.new("Props")
bpy.context.scene.collection.children.link(col)

obj = bpy.data.objects["Chair"]
bpy.context.scene.collection.objects.unlink(obj)
col.objects.link(obj)
```

## Batch Operations Pattern

For 10+ similar objects, build in a loop within one `execute_blender_code` call:

```python
import math

for i in range(12):
    angle = 2 * math.pi * i / 12
    x = 5 * math.cos(angle)
    y = 5 * math.sin(angle)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=3, location=(x, y, 1.5))
    col = bpy.context.active_object
    col.name = f"Column_{i:02d}"
    col.rotation_euler = (0, 0, angle)
```

This avoids multiple MCP round-trips for homogeneous operations.
