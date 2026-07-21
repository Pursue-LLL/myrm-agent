# Worked Recipes

Complete build sequences from a natural-language brief to a delivered capture.
Each step uses the discovery contract: locate capabilities via
`list_toolsets`/`describe_toolset`, then invoke with exact values.

## Recipe Grammar

Every step = four parts:

    INTENT     what this step achieves
    DISCOVER   which toolset/tool capability to use
    VALUES     exact arguments and numbers
    VERIFY     query or screenshot proving it worked

**Lighting rule for every recipe:** set **Mobility = Movable** on every light
(Lumen GI ignores Static/Stationary).

**Session preamble (do once):**

1. `list_toolsets` → note qualified names.
2. `describe_toolset` on each group you'll use → cache schemas.
3. Query current level; inventory environment actors. **Configure existing;
   spawn only what's missing** (templates ship with most).
4. Read existing sun's intensity → learn calibration convention.
5. Locate `CaptureViewport` for virtual-camera verification.

Save after every phase marked 💾. One tool call at a time.

---

## Recipe A — Daylight Exterior Clearing

Brief: "a sunny clearing with some rocks and a path"

**Phase 1 — Environment shell**

- VALUES: spawn SkyAtmosphere, SkyLight (real-time capture), DirectionalLight
  rotation (0, −55, 40), intensity 90,000 lux, 5,800 K, atmosphere sun light on;
  ExponentialHeightFog density 0.008.
- VERIFY: screenshot reads as daytime sky.

**Phase 2 — Ground & blocking**

- VALUES: `/Engine/BasicShapes/Plane.Plane` at (0,0,0), scale (100,100,1) →
  100×100m ground. 5–9 cubes with varied scales as rocks. Path: flattened cubes.
- VERIFY: eye-height screenshot, nothing floats, scale sane. 💾

**Phase 3 — Exposure**

- VALUES: PPV unbound, Manual, EV100 = 14.5.
- VERIFY: bright but not blown.

**Phase 4 — Deliver**

- VALUES: `HighResShot 3840x2160` from framed viewpoint.
- VERIFY: vision check against brief. 💾

---

## Recipe B — Moody Practical-Lit Interior

Brief: "dim cozy room at night, warm lamp, blue moonlight through window"

**Phase 1 — Room shell from primitives**

- VALUES: Floor cube at (0,0,−10) scale (6,6,0.2). Walls 280 cm tall. Window
  gap 120×120 cm at sill 90 cm.

**Phase 2 — Lighting**

- Kill sun: intensity → 0.05 lux, 4,300 K, pitch −20° through window.
- Warm practical: PointLight 800 lumens, 2,700 K, radius 600 cm.
- Cool window: SpotLight 2,000 lumens, 6,500 K.
- Exposure: PPV EV100 = 4.5, fog density 0.015 + volumetric.
- VERIFY: warm pool + cool slash. 💾

**Phase 3 — Dress & deliver**

- Swap materials if Starter Content exists. Final HighResShot. 💾

---

## Recipe C — Golden-Hour Cinematic Still

Brief: "golden hour cinematic shot of <subject>"

**Phase 1 — Relight**

- VALUES: sun 12,000 lux, 3,200 K, pitch −8°, fog 0.02 + volumetric, EV100 11.

**Phase 2 — Camera**

- Use `CaptureViewport` with `captureTransform` as virtual camera.
- Frame subject on thirds, slight upward pitch.

**Phase 3 — Deliver**

- HighResShot or CaptureViewport at final resolution. 💾

---

## Recipe D — Import Asset and Populate

Brief: "put a ring of <model> around the fountain"

**Phase 1 — Import**

- Import with `automated=True` to `/Game/Imported`. Verify scale against
  180 cm yardstick.

**Phase 2 — Populate**

- Ring of N instances: angle θ=360·i/N, position = center + (r·cosθ, r·sinθ, 0).
- Spawn one, verify facing, then loop the rest.

**Phase 3 — Deliver**

- Count query, overhead + eye-level screenshots. 💾
