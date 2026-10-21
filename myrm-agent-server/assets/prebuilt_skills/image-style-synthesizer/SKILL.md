---
name: image-style-synthesizer
description: >-
  Enterprise-grade structured Prompt-as-Code image synthesis and visual schema
  workflow. Deconstructs ambiguous natural language requests into atomic visual
  schemas (subject, style, lighting, material, composition, negative gating) and
  applies industrial-grade commercial presets for high-consistency image generation.
version: 1.0.0
category: productivity
tags:
  - image
  - prompt-as-code
  - visual-schema
  - design
  - commercial-presets
  - multi-modal
allowed-tools: image_tool file_write_tool
contract:
  steps:
    - "Phase 1: Visual Intent Extraction — parse natural language input to identify core subject, intended use-case (banner, icon, blog header, UI illustration), and aspect ratio"
    - "Phase 2: Atomic Schema Compilation — compile user intent into the six-dimensional Prompt-as-Code schema (Subject, Style Preset, Lighting, Material, Composition, Negative Gating)"
    - "Phase 3: Typography & Safety Gating — enforce typography restrictions (max 3 uppercase words) and inject essential negative prompt tokens to eliminate artifacts and gibberish"
    - "Phase 4: Synthesis Tool Invocation — invoke image_tool(action='generate', prompt=compiled_prompt, size=target_size) with the assembled prompt string"
    - "Phase 5: Artifact Registration & Presentation — verify generated image output, register under artifacts/images/ directory, and present visual preview with style rationale to the user"
  potential_traps:
    - description: "Unconstrained english text generation causing warped, misspelled lettering in generated images"
      mitigation: "Strict Typography Gate: enforce a maximum of 3 explicit words, and automatically inject 'distorted text, blurry letters, spelling mistakes, watermark' into negative prompt"
      severity: high
    - description: "Overly verbose prose prompts diluting diffusion attention weights"
      mitigation: "Atomic Tokenization: assemble prompt using weighted keyword clauses rather than rambling narrative sentences"
      severity: medium
    - description: "Failure when local or cloud image generation provider encounters quota or API errors"
      mitigation: "Graceful Fallback: report detailed provider status and present compiled visual schema so the user can inspect or retry manually"
      severity: low
  verification_steps:
    - step_id: schema_compiled
      description: "Visual intent is compiled into 6-dimensional schema before calling tool"
      validation_method: "Prompt reflects subject, style, lighting, material, composition, and negative gating"
      is_required: true
    - step_id: tool_invoked
      description: "image_tool is invoked with compiled prompt and valid aspect ratio"
      validation_method: "Tool execution returns image url or task id"
      is_required: true
  success_criteria: "Spoken or text image request is compiled into structured Prompt-as-Code and converted into a commercial-grade visual asset"
  estimated_duration_seconds: 60
---

# Structured Prompt-as-Code Image Synthesis & Visual Schema

## Overview

Upgrades casual, unstructured image generation prompts into production-ready **Prompt-as-Code** specifications. Eliminates random style drift, deformed artifacts, and garbled text by decomposing visual requests into an atomic six-dimensional schema with proven commercial design presets.

---

## Operating Protocol

### Phase 1: Visual Intent Extraction

Identify the exact commercial objective from user instructions:
- **Target Deliverable**: Product launch banner, UI feature illustration, tech blog hero image, commercial avatar, or architectural concept.
- **Aspect Ratio Selection**:
  - Landscape (`1792x1024` or `16:9`): Blog headers, hero sections, presentation slides.
  - Square (`1024x1024` or `1:1`): Avatars, icons, social media square posts.
  - Portrait (`1024x1792` or `9:16`): Mobile splash screens, poster layouts.

---

### Phase 2: Atomic Schema Compilation (Prompt-as-Code)

Translate the creative brief into a six-dimensional visual specification:

```yaml
subject: "Focal entity, precise pose, key activity, state of motion"
style: "Commercial design preset (e.g., 3D Claymorphism, Minimalist Flat, Cyberpunk Neon)"
lighting: "Volumetric rim lighting, soft studio diffused, golden hour, or dual-tone neon"
material: "Frosted translucent acrylic, matte aluminum, polished ceramic, liquid glass"
composition: "Isometric 45-degree, golden ratio rule of thirds, clean negative space"
negative: "blurry, low quality, distorted anatomy, gibberish letters, ugly watermark"
```

#### Supported Commercial Presets
1. **3D Claymorphism / Neumorphism**: Matte pastel materials, inflated soft 3D shapes, clean studio key light.
2. **Enterprise Isometric Tech**: Floating hexagonal modules, translucent glowing glass conduits, clean dark-navy background.
3. **Minimalist Flat Vector**: Bold shapes, 3-color limited palette, sharp lines, Swiss graphic design aesthetic.
4. **Cinematic Realism**: 85mm portrait lens, f/1.8 bokeh, dramatic rim lighting, film grain texture.
5. **Cyberpunk Industrial**: Rain-slicked reflective surfaces, dual-tone cyan/magenta neon, high contrast.
6. **Hand-drawn Architectural Wireframe**: Fine architectural ink drafting, blueprint grid accents, subtle blueprint wash.
7. **Abstract Generative Gradients**: Flowing silk curves, chromatic aberration, iridescence, ethereal depth.
8. **E-Commerce Studio Product**: Neutral seamless backdrop, dual softbox lighting, ultra-sharp edge definition.

---

### Phase 3: Typography & Negative Safety Gating

#### Typography Restriction Gate
Diffusion models struggle with arbitrary long sentences.
- **Rule**: If text is requested inside the image, limit strictly to **<= 3 words** (e.g., `"MYRM"`, `"AI AGENT"`).
- **Enforcement**: If the user asks for full slogans or paragraphs, instruct the model to render the visual background only, and advise that typography be overlaid in post-processing.
- **Negative Gate**: Always ensure negative tokens include:
  `blurry, distorted text, spelling error, deformed hands, extra limbs, watermark, artifacts, lowres`

---

### Phase 4: Image Tool Invocation

Assemble the compiled tokens into a cohesive prompt string and execute `image_tool`:

```python
# Compiled prompt structure:
compiled_prompt = f"{subject}, {style}, {lighting}, {material}, {composition}, clean background"
image_tool(action="generate", prompt=compiled_prompt, size=target_size, quality="hd")
```

---

### Phase 5: Artifact Registration & Presentation

1. Upon receiving the generated image URL or data, report the relative path (e.g. `artifacts/images/YYYY-MM-DD-{style-slug}.png`).
2. Present a concise explanation to the user:
   - **Applied Style Preset** (e.g. `3D Isometric Tech Illustration`);
   - **Key Visual Elements & Lighting Choices**;
   - **Aspect Ratio & Resolution**.
