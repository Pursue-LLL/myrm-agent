# image/

## Overview

Image generation and editing; one call produces one image. `generator.py` runs a request with failover and stores the
result through the media callback (fail-closed). Text-to-image is the async path: `async_image_engine.py` enqueues via
`toolkits/tasks/` — full chain in [TASK_QUEUE_SYSTEM.md](../../tasks/TASK_QUEUE_SYSTEM.md). `image_engine.py` is the
synchronous edit and model-listing surface. Reference inputs arrive as bytes already resolved by `media_inputs.py`.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| async_image_engine.py | Core | Async enqueue of one image per call: writes execution snapshot + request into TaskStore and returns the task id; optional `payload_postprocessor` seals secrets before persist (server injects) | ✅ |
| generator.py | Core | Image generation and editing engine. Calls `transport/images.py`; routes reference images to the edit endpoint and refuses a model that accepts none (a `MediaInputError`: no retry can fix it); `quality` reaches the edit request as it does the generation request; status-code retry classification, gateway-to-BYOK fallback, model failover, and persistence once on the final result (a storage failure never regenerates or falls back). | ✅ |
| image_engine.py | Core | Synchronous `edit_image` (pre-validated) and `list_models` for the server media_tools adapter; returns the same result shape an async task does. | ✅ |
| models.py | Core | Pure data types: ImageResult (with the stored reference), ImageGenerationConfig (required model, gateway_config support), errors. | — |
| types.py | Config | Capability schema and built-in profiles for image models; `editable_model_names` lists the models that edit. | — |
| validator.py | Core | 3-layer pre-call validation of an edit (L1 prompt, L2 capability, L3 input MIME/size). | ✅ |

## Key Dependencies

- `core.security.http.secure_fetch` (secure_get for provider result URL downloads)
- `media_inputs` (the business layer resolves reference inputs with it before calling the engine; `generator.py` raises its `MediaInputError` for a model that accepts no input images)
- `core`
