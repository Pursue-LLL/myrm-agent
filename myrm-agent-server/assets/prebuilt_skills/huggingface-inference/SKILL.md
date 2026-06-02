---
name: huggingface-inference
description: >-
  Directly call Hugging Face Serverless Inference API for multi-modal tasks.
  Supports text-to-image (e.g. stabilityai/stable-diffusion-3.5-large), text-to-speech,
  image classification, object detection, and more. Zero local dependencies.
version: 1.0.0
category: mlops
tags:
  - huggingface
  - api
  - inference
  - multi-modal
  - image-generation
  - stable-diffusion
allowed-tools: huggingface_inference_tool
contract:
  steps:
    - "Phase 1: Validation — Check if HF_TOKEN is configured in environment/settings"
    - "Phase 2: Model Selection — Determine the best HF model ID for the user's task"
    - "Phase 3: Parameter Construction — Build the appropriate JSON payload for the chosen model task"
    - "Phase 4: API Invocation — Call the huggingface_inference_tool"
    - "Phase 5: Output Handling — Present the resulting URL (for images/audio) or text to the user"
  potential_traps:
    - description: "Model is too large or requires Pro subscription to run on free Serverless API"
      mitigation: "If a 503 or model loading error occurs, fallback to a smaller or more popular model"
      severity: medium
  success_criteria: "Successful invocation of the HF inference API and rendering of the output"
  estimated_duration_seconds: 30
---

# Hugging Face Serverless Inference

## Overview

This skill allows the Agent to natively call thousands of machine learning models hosted on the Hugging Face Hub using the Serverless Inference API, without downloading heavy weights or installing local deep learning dependencies (PyTorch/Transformers).

It is the optimal path for executing multi-modal tasks like Image Generation, Audio Generation, or specialized Text Classification.

## Configuration Requirements

To use this skill, the user must have their Hugging Face Access Token configured.
The `huggingface_inference_tool` will automatically read the `HF_TOKEN` from the environment or user settings.

If the tool reports authentication errors, instruct the user to configure their Hugging Face token in the settings.

## Workflow

### 1. Model Selection
Choose an appropriate model based on the user's request. Examples:
- **Text-to-Image**: `stabilityai/stable-diffusion-3.5-large`, `black-forest-labs/FLUX.1-dev`
- **Text-to-Speech**: `suno/bark`, `facebook/mms-tts-eng`
- **Image Classification**: `google/vit-base-patch16-224`

### 2. Payload Construction
The tool accepts a generic `inputs` field and an optional `parameters` object.
For Text-to-Image, `inputs` should be the prompt string.

Example payload construction:
```json
{
  "model_id": "stabilityai/stable-diffusion-3.5-large",
  "task": "text-to-image",
  "inputs": "A cyberpunk cat in neon city",
  "parameters": {}
}
```

### 3. Execution & Presentation
Call the tool. If the tool generates an image or audio, it will return a base64 encoded data URI or a local temporary file path.
Present this media directly to the user using Markdown image syntax: `![Generated Image](data:image/jpeg;base64,...)` or by passing the file path if supported by the channel.

### 4. Error Handling
- **Model Loading (503)**: HF Serverless API models sleep when inactive. The tool might return an "estimated_time" indicating the model is loading. The tool handles retry logic internally, but if it ultimately fails, suggest a different model.
- **Authentication (401)**: Remind the user to set `HF_TOKEN`.
