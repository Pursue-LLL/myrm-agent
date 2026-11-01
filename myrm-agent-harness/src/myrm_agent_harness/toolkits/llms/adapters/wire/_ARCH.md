# wire/

## Overview
OpenCode multi-wire transport for TransportChatModel: Responses API (`/v1/responses`) and Anthropic Messages (`/v1/messages`).

## File Index

| File | Role | Description |
|------|------|-------------|
| __init__.py | Package | Re-exports wire transport helpers (params, translator, normalizer). |
| translator.py | Core | Chat messages → Responses input; reasoning item replay; tool_calls/function_call_output; system → instructions |
| normalizer.py | Core | Responses payload/events → chat-completions shape; decouple reasoning summary into reasoning_content; preserve `responses_reasoning_items`; failed/error SSE → ResponsesStreamError |
| params.py | Core | Build Responses-wire request kwargs (reasoning, include, api_base endpoint strip) from TransportChatModel call params |
| anthropic_params.py | Core | Anthropic Messages wire overrides for OpenCode Go minimax/qwen |
| routing.py | Core | `resolve_wire`: the protocol a call must use. The configured protocol is a preference; models the catalog lists as Responses-only, xAI native search and the GPT-5.4+ function-tools-with-reasoning combination move to the Responses endpoint, and a Responses call to a provider without that endpoint falls back to chat completions |
| invocation.py | Core | Sync/async invoke + stream adapters; fail-open retry on `invalid_encrypted_content` |

## POS
Harness-only protocol layer. Vendor routing tables live in server `app/core/wire/`.
