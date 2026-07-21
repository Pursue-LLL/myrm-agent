# Scene-Craft Cheat Sheet

Physical values and conventions for scenes that read as *good* instead of merely
present. UE units, real-world references, and practical ranges.

## Units & Conventions

| Thing | Convention |
|-------|-----------|
| Distance | 1 UU = **1 cm** |
| Axes | **Z-up**, X-forward, Y-right (left-handed) |
| Rotation | Degrees: Roll (X), Pitch (Y), Yaw (Z) |
| Color | Linear RGBA, 0–1 per channel |
| Light color | Prefer `use_temperature` + Kelvin over tinting RGB |

Directional-light aiming: Pitch −90° = noon overhead; −5° to −15° = golden
hour; yaw = compass direction.

## Human-Scale Reference

| Reference | Size (cm) |
|-----------|-----------|
| Eye height | 160–175 |
| Door | 200–210 × 80–90 |
| Ceiling (residential) | 240–300 |
| Building storey | 300–400 |
| Counter/desk | 75–110 |
| UE mannequin | ≈180 |
| Car | ≈450 × 180 × 145 |

## Content Paths

| Root | Meaning |
|------|---------|
| `/Game/...` | Project content |
| `/Engine/...` | Engine-shipped content |
| `/Script/Module.Class` | Native classes |

Engine primitives (always available, great for blocking):

    /Engine/BasicShapes/Cube.Cube          (100×100×100 cm)
    /Engine/BasicShapes/Sphere.Sphere      (100 cm diameter)
    /Engine/BasicShapes/Cylinder.Cylinder  (100 cm ⌀ × 100 cm)
    /Engine/BasicShapes/Plane.Plane        (100×100 cm)

Common actor classes: `StaticMeshActor`, `PointLight`, `SpotLight`,
`RectLight`, `DirectionalLight`, `SkyLight`, `ExponentialHeightFog`,
`SkyAtmosphere`, `PostProcessVolume`, `CameraActor`, `CineCameraActor`.

## Lighting — Physical Values

UE5 defaults to physical units. **Calibration rule:** read the existing sun's
intensity first — template worlds often use `intensity: 10`, not physical lux.
If low-calibration, work RELATIVE (golden hour ≈ 0.5×, overcast ≈ 0.3×).

### Sun (DirectionalLight, lux)

| Condition | Lux | Pitch | Temperature |
|-----------|-----|-------|-------------|
| Noon | 75,000–120,000 | −60° to −90° | 5,500–6,000 K |
| Afternoon | 40,000–75,000 | −30° to −50° | 5,000–5,500 K |
| Golden hour | 5,000–20,000 | −5° to −15° | 2,800–3,500 K |
| Overcast | 5,000–20,000 | −45° | 6,500–7,500 K |
| Blue hour | 10–100 | −2° to +5° | 8,000–12,000 K |
| Full-moon | 0.05–0.3 | −30° to −60° | 4,000–4,500 K |

### Local Lights (lumens)

| Source | Lumens | Temperature |
|--------|--------|-------------|
| Candle | 10–15 | 1,850 K |
| 40W bulb equiv. | 450 | 2,700 K |
| 60W equiv. | 800 | 2,700–3,000 K |
| 100W equiv. | 1,600 | 3,000 K |
| Ceiling fixture | 2,000–4,000 | 3,000–4,000 K |
| Office fluorescent | 2,500–5,000 | 4,000–5,000 K |
| Streetlight | 5,000–15,000 | 2,000 K |
| Campfire | 100–300 | 1,700–2,000 K |

### Exposure (PostProcessVolume)

Manual exposure preferred for deterministic agent work:

| Scene | EV100 |
|-------|-------|
| Bright sun | 14–16 |
| Overcast | 11–13 |
| Golden hour | 10–12 |
| Bright interior | 7–9 |
| Dim interior | 4–6 |
| Night street | 2–4 |
| Moonlit | −2 to 0 |

### GI & Reflections

UE5 uses **Lumen** GI + reflections by default. **Critical:** Lumen GI only
considers lights with **Movable** mobility. Set Mobility = Movable on every
light you place.

### Fog & Atmosphere

- `SkyAtmosphere` for physical sky. Pair with DirectionalLight
  `atmosphere_sun_light = true`.
- `ExponentialHeightFog`: density 0.005–0.015 subtle, 0.02–0.05 moody,
  0.05–0.2 heavy. Enable Volumetric Fog for light shafts.
- `VolumetricCloud` for sky clouds (exterior, costs GPU).

## Mood Recipes

| Mood | Sun/Key | Fog | EV100 |
|------|---------|-----|-------|
| Crisp noon | 100k lux, pitch −70°, 5,800 K | 0.005 | 15 |
| Golden hour | 10k lux, pitch −8°, 3,200 K | 0.02 + volumetric | 11 |
| Overcast | 10k lux, 7,000 K | 0.01 | 12 |
| Night, moonlit | 0.25 lux, 4,300 K + practicals | 0.015 | −1 to 1 |
| Horror interior | No sun; 1–2 practicals | 0.03–0.06 volumetric | 4–5 |

## Camera & Framing (CineCameraActor)

| Intent | Focal length | Aperture |
|--------|-------------|----------|
| Wide establishing | 18–28 mm | f/5.6–8 |
| Neutral "eye" | 35–50 mm | f/4 |
| Portrait isolation | 85–135 mm | f/1.4–2.8 |

Focus: Manual focus distance = distance to subject in cm. Keep horizon off
dead-center; subjects on thirds. Slight camera pitch (−2° to −8°) for
interiors.

## Capture & Render

- **CaptureViewport**: returns base64 PNG + camera metadata. Supports arbitrary
  `captureTransform` without moving user's viewport.
- **HighResShot**: `HighResShot 3840x2160` → `<Project>/Saved/Screenshots/`.
- **Movie Render Queue**: quality path for sequences/finals.
