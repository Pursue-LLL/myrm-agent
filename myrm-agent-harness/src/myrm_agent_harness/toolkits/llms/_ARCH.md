# llms/

## Overview
The LLM layer. `transport/` reaches every provider over `httpx` without a provider SDK, `catalog/` holds the model facts,
`core/` is the model factory and credential pool, `adapters/` fit the transport to LangChain, `errors/` classifies failures,
`fallback/` switches models on failure, `routing/` picks a model before the agent runs, and `image/`, `video/`, `tts/` and `vision/` are the media engines.

Bug ledgers (local-only: git-ignored and excluded from the wheel): `llms_<start>_<end>_BUGFIX_LOG.md` in this directory, one file per 7-day window.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| media_task_types.py | Core | Image async-job payload/result DTOs for `toolkits/tasks` integration | ✅ |
| capability_learner.py | Core | In-process model capability cache — records runtime-discovered capabilities (e.g. rejects_media, rejects_allowed_tools_tool_choice) with TTL. | ✅ |
| allowed_tools_capability.py | Core | Provider gate for OpenAI ``tool_choice.type=allowed_tools``; execution-layer policy remains authoritative when skipped. | ✅ |
| text_completion.py | Core | `acomplete_text`: one-shot plain chat request through the transport, outside the chat adapter (eval judge, spoken-summary rewrite, policy draft) | ✅ |
| ephemeral_output_tokens.py | Core | ContextVar override for truncation-recovery output budget; read by `TransportChatModel`. | ✅ |
| secrets.py | Core | Framework-neutral external secret reference resolution (`op://` 1Password / `bw://` Bitwarden) with Zero-Disk plaintext; stdlib-only, re-exported by `backends/secrets`. | ✅ |

| Submodule | Description |
|-----------|-------------|
| probe/ | Lightweight provider balance probe contracts and normalized data models. |
| transport/ | Typed protocol wires over `httpx` for every provider (OpenAI chat/Responses, Anthropic Messages, Gemini, Ollama, AWS Bedrock Converse), embeddings, rerank and image calls. See [transport/_ARCH.md](transport/_ARCH.md). |
| catalog/ | Model facts (context windows, output ceilings, prices, capability flags): bundled snapshot plus runtime registrations. See [catalog/_ARCH.md](catalog/_ARCH.md). |
| consensus/ | Multi-model consensus (MoA) inference — parallel reference queries + aggregator synthesis (arXiv:2406.04692). |
| _media_shared/ | Provider mode-capability types and the normalization engine that video generation uses to fit requested parameters to the values a provider supports. |
| adapters/ | LLM layer: LangChain , messageconverts, handles, toolcallsparse, Schema normalize; **wire/** Responses API transport; `image_payload_evictor.py` framework-neutral 400/413 image eviction |
| core/ | LLM core: LLM classes, strategy-aware manager, and credential pool. |
| errors/ | LLM error processing layer: three-tier error classification, fault-tolerant calls, and standardized  |
| fallback/ | Enhanced model fallback management. Contains ManagedLLM with Direct Preflight Guard (zero-cost local token overflow prevention), cooldown periods, candidate pools, and decision logging. Health probe is structured (`probe_llm_health` → `HealthProbeResult`): it separates a deadline miss (`timeout`) from an upstream rejection (`provider_error`) and keeps the provider's own reason, so callers can explain an unreachable model instead of reporting a flat "no response" |
| rate_limit/ | Proactive rate-limit tracking: provider rate-limit headers parsed into bucket state, kept by an in-memory tracker. See [rate_limit/_ARCH.md](rate_limit/_ARCH.md). |
| reliability/ | Jittered retry delays (`calculate_jittered_delay`) and the long adaptive ladder for PAAS overload errors. See [reliability/_ARCH.md](reliability/_ARCH.md). |
| image/ | Image submodule. |
| routing/ | Pre-agent routing layer: task complexity routing and privacy routing. |
| utils/ | LLM toollayer: JSON handles, modelparameter, log |
| video/ | Video generation module — multi-provider video generation with failover. |
| tts/ | Audio generation module — OpenAI/ElevenLabs TTS with gateway fallback. See [tts/_ARCH.md](tts/_ARCH.md). |
| vision/ | Multimodal understanding — `VisionFallbackEngine` / `VideoAnalysisEngine`. See [vision/_ARCH.md](vision/_ARCH.md). |

## Media stack (generation vs understanding)

| Layer | Location | Role |
|-------|----------|------|
| **Generation** | `image/`, `video/`, `tts/` | LLM engines for image, video, and audio creation (LangChain adapters in server `media_tools/`) |
| **Shared media** | `_media_shared/` | Mode-capability types and parameter normalization used by `video/` |
| **Understanding** | `vision/` | Text-mode fallback when the primary model lacks vision; consumed by `file_read_tool`, server chat utils |
