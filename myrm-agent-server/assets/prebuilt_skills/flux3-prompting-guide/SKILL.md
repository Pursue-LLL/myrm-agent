---
name: flux3-prompting-guide
description: >-
  Professional prompting guide and continuity workflow SOP for FLUX.3 Video,
  keyframes interpolation, and multi-clip video continuation.
  FLUX.3 视频与连续分镜提示词指南：角色一致性、首尾帧过渡与镜头无缝续写。
version: 1.0.0
category: creative
tags:
  - video
  - flux3
  - prompting
  - keyframes
  - continuation
  - consistency
  - 分镜
  - 角色一致性
allowed-tools: video_tool image_tool ask_question_tool file_read_tool
contract:
  steps:
    - "Phase 1: Character & Scene Anchoring — define immutable character features and environmental lighting"
    - "Phase 2: Shot Planning — determine mode: Text-to-Video (T2V), Image-to-Video (I2V), Keyframes (K2V), or Continuation"
    - "Phase 3: Prompt Engineering — craft dynamic motion cues, camera movement, and temporal evolution"
    - "Phase 4: Synthesis & Extension — invoke video_tool and chain subsequent clips using continuation"
  potential_traps:
    - description: "Contradictory motion cues in single 5-10s clip"
      mitigation: "Limit each clip to one primary camera movement and one focal action"
      severity: medium
    - description: "Character drift during video continuation"
      mitigation: "Reuse the terminal frame of the previous clip as continuation source and keep character anchors constant"
      severity: high
  verification_steps:
    - step_id: provider_check
      description: "Ensure video provider (FAL.ai or alternative) is configured in Settings"
      validation_method: "Verify provider status via media provider configuration"
      is_required: true
  success_criteria: "High-fidelity, cinematic video clips generated with smooth transitions and character consistency"
  estimated_duration_seconds: 180
---

# FLUX.3 Video & Cinematic Continuation Guide

A systematic workflow and prompting guide for generating coherent, cinematic videos with FLUX.3, keyframe interpolation, and seamless clip continuation.

## When to Use

Trigger this skill whenever the user asks to:
1. Generate high-quality cinematic videos using FLUX.3 or advanced video models.
2. Maintain character, vehicle, or scene consistency across multiple video clips.
3. Interpolate smoothly between two keyframe images (start frame and end frame).
4. Extend/continue an existing video without character deformation or jump cuts.

---

## Shot Modes & Workflows

### 1. Keyframes Interpolation (Start Frame → End Frame)
- **Goal**: Smoothly transform from State A to State B without chaotic hallucinations.
- **Workflow**:
  1. Prepare or generate Start Image and Terminal Image.
  2. Call `video_tool` with `keyframes=[start_image, end_image]`.
  3. Prompt structure: `[Initial state] transitioning into [intermediate action] and ending with [terminal state], [lighting/camera cues]`.
- **Example**:
  > *"A cyberpunk mechanical hummingbird hovering calmly over a neon orchid, then flapping rapidly and diving downward towards a rain-slicked Tokyo street, ending in a high-speed banking turn into the neon mist. Cinematic 8k, photorealistic reflections."*

### 2. Video Continuation (Seamless Sequence Extension)
- **Goal**: Extend a 5-second video into a 10s, 15s, or longer continuous sequence.
- **Workflow**:
  1. Generate Clip 1.
  2. Extract or retain the terminal video asset.
  3. Pass the video as reference with `continuation=True` to generate Clip 2.
  4. Ensure prompt maintains exact character anchors (clothing, color, features) and only advances temporal actions.

---

## Standard Prompting Vocabulary

### Camera Movement Tokens
- **Static / Subtle**: `static tripod shot`, `subtle handheld camera breathing`, `slow cinematic push-in`
- **Linear Motion**: `smooth dolly forward`, `dolly zoom vertigo effect`, `slow pan left following the subject`
- **Dynamic Action**: `orbital tracking shot 360 degrees`, `crane shot descending from sky to street level`, `fpv drone racing perspective`

### Lighting & Atmospheric Cues
- `volumetric fog catching golden hour light`
- `anamorphic lens flare, shallow depth of field, f/1.4 bokeh`
- `dramatic chiaroscuro lighting, cinematic film grain, 35mm film aesthetic`
