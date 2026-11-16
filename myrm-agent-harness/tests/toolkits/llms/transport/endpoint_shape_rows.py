"""Rows of the endpoint-shape tests: an address a user pastes, and the URL the request must reach.

Every row states a shape people actually paste (an API root, a full operation URL, the Azure portal's *Target URI*,
a Google AI Studio OpenAI-compatibility base, ...) and the exact URL the request must reach. ``basis`` says what
makes the expectation right, so a reviewer can tell an authority from a design choice:

- ``sdk``      the OpenAI SDK's rule: ``base_url`` + operation path, a query is the client's ``default_query``;
- ``azure``    Microsoft Learn's Azure OpenAI URL forms (``/openai/deployments/{name}/...?api-version=``, the v1 route);
- ``google``   answered by the live Gemini API: ``/v1beta/models/{m}:generateContent`` is routed (403 without a key)
               while the same path under ``/v1beta/openai`` is 404, so the OpenAI-compatibility base is not a native root;
- ``frontend`` what the UI's former ``normalizeApiUrl`` produced for the same text (it ran before the harness did);
- ``design``   a choice with no external authority, kept explicit so it is not mistaken for a standard.
"""

from __future__ import annotations

from typing import NamedTuple

GENERIC_MODEL = "mystery/chat-1"
AZURE_DEFAULT_QUERY = "?api-version=2025-02-01-preview"
GEMINI_HOST = "https://generativelanguage.googleapis.com"


class Shape(NamedTuple):
    name: str
    model: str
    pasted: str
    reaches: str
    basis: str


OPENAI_COMPATIBLE = [
    Shape("root", GENERIC_MODEL, "https://host.example/v1", "https://host.example/v1/chat/completions", "sdk"),
    Shape(
        "trailing slash", GENERIC_MODEL, "https://host.example/v1/", "https://host.example/v1/chat/completions", "sdk"
    ),
    Shape("host only", GENERIC_MODEL, "https://host.example", "https://host.example/chat/completions", "sdk"),
    Shape(
        "port and prefix",
        GENERIC_MODEL,
        "http://10.0.0.5:8080/gw/v1",
        "http://10.0.0.5:8080/gw/v1/chat/completions",
        "sdk",
    ),
    Shape(
        "chat operation",
        GENERIC_MODEL,
        "https://host.example/v1/chat/completions",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "chat operation, slash",
        GENERIC_MODEL,
        "https://host.example/v1/chat/completions/",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "responses operation",
        GENERIC_MODEL,
        "https://host.example/zen/go/v1/responses",
        "https://host.example/zen/go/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "OpenCode Go responses URL",
        GENERIC_MODEL,
        "https://opencode.ai/zen/go/v1/responses/",
        "https://opencode.ai/zen/go/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "completions operation",
        GENERIC_MODEL,
        "https://host.example/v1/completions",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "models list",
        GENERIC_MODEL,
        "https://host.example/v1/models",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "embeddings operation",
        GENERIC_MODEL,
        "https://host.example/v1/embeddings",
        "https://host.example/v1/chat/completions",
        "frontend",
    ),
    Shape(
        "query is the default_query",
        GENERIC_MODEL,
        "https://host.example/v1?team=a&x=1",
        "https://host.example/v1/chat/completions?team=a&x=1",
        "sdk",
    ),
    Shape(
        "operation and query",
        GENERIC_MODEL,
        "https://host.example/v1/chat/completions?team=a",
        "https://host.example/v1/chat/completions?team=a",
        "sdk",
    ),
    Shape(
        "fragment is never sent",
        GENERIC_MODEL,
        "https://host.example/v1#section",
        "https://host.example/v1/chat/completions",
        "design",
    ),
    Shape(
        "credentials in the address are kept",
        GENERIC_MODEL,
        "https://u:p@host.example/v1",
        "https://u:p@host.example/v1/chat/completions",
        "design",
    ),
]

AZURE = [
    Shape(
        "resource root",
        "azure/gpt-4o",
        "https://res.openai.azure.com",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{AZURE_DEFAULT_QUERY}",
        "azure",
    ),
    Shape(
        "resource root, slash",
        "azure/gpt-4o",
        "https://res.openai.azure.com/",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{AZURE_DEFAULT_QUERY}",
        "azure",
    ),
    Shape(
        "/openai prefix",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{AZURE_DEFAULT_QUERY}",
        "azure",
    ),
    Shape(
        "v1 route",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai/v1/",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{AZURE_DEFAULT_QUERY}",
        "azure",
    ),
    Shape(
        "deployment root",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai/deployments/gpt-4o",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{AZURE_DEFAULT_QUERY}",
        "azure",
    ),
    Shape(
        "portal Target URI",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21",
        "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21",
        "azure",
    ),
    Shape(
        "version only",
        "azure/gpt-4o",
        "https://res.openai.azure.com?api-version=2024-10-21",
        "https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21",
        "azure",
    ),
    Shape(
        "the model field names the deployment",
        "azure/gpt-4o",
        "https://res.openai.azure.com/openai/deployments/other/chat/completions",
        f"https://res.openai.azure.com/openai/deployments/gpt-4o/chat/completions{AZURE_DEFAULT_QUERY}",
        "design",
    ),
]

GEMINI_NATIVE = [
    Shape(
        "official host only",
        "gemini/gemini-2.0-flash",
        GEMINI_HOST,
        f"{GEMINI_HOST}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "official root",
        "gemini/gemini-2.0-flash",
        f"{GEMINI_HOST}/v1beta/",
        f"{GEMINI_HOST}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "models list",
        "gemini/gemini-2.0-flash",
        f"{GEMINI_HOST}/v1beta/models",
        f"{GEMINI_HOST}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "pasted generateContent URL",
        "gemini/gemini-2.0-flash",
        f"{GEMINI_HOST}/v1beta/models/gemini-pro:generateContent",
        f"{GEMINI_HOST}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "pasted streaming URL",
        "gemini/gemini-2.0-flash",
        f"{GEMINI_HOST}/v1beta/models/gemini-pro:streamGenerateContent",
        f"{GEMINI_HOST}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "OpenAI-compatibility base",
        "gemini/gemini-2.0-flash",
        f"{GEMINI_HOST}/v1beta/openai/",
        f"{GEMINI_HOST}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "OpenAI-compatibility operation",
        "gemini/gemini-2.0-flash",
        f"{GEMINI_HOST}/v1beta/openai/chat/completions",
        f"{GEMINI_HOST}/v1beta/models/gemini-2.0-flash:generateContent",
        "google",
    ),
    Shape(
        "a relay's host is not guessed",
        "gemini/gemini-2.0-flash",
        "https://relay.example",
        "https://relay.example/models/gemini-2.0-flash:generateContent",
        "design",
    ),
    Shape(
        "a relay's versioned root",
        "gemini/gemini-2.0-flash",
        "https://relay.example/v1beta",
        "https://relay.example/v1beta/models/gemini-2.0-flash:generateContent",
        "design",
    ),
]

NATIVE_WIRES = [
    Shape(
        "anthropic root",
        "anthropic/claude-sonnet-4-5",
        "https://api.anthropic.com",
        "https://api.anthropic.com/v1/messages",
        "frontend",
    ),
    Shape(
        "anthropic /v1",
        "anthropic/claude-sonnet-4-5",
        "https://api.anthropic.com/v1",
        "https://api.anthropic.com/v1/messages",
        "frontend",
    ),
    Shape(
        "anthropic operation",
        "anthropic/claude-sonnet-4-5",
        "https://api.anthropic.com/v1/messages",
        "https://api.anthropic.com/v1/messages",
        "frontend",
    ),
    Shape(
        "anthropic models list",
        "anthropic/claude-sonnet-4-5",
        "https://api.anthropic.com/v1/models",
        "https://api.anthropic.com/v1/messages",
        "frontend",
    ),
    Shape("ollama root", "ollama/llama3", "http://localhost:11434", "http://localhost:11434/api/chat", "frontend"),
    Shape("ollama /v1", "ollama/llama3", "http://localhost:11434/v1", "http://localhost:11434/api/chat", "frontend"),
    Shape(
        "ollama OpenAI operation",
        "ollama/llama3",
        "http://localhost:11434/v1/chat/completions",
        "http://localhost:11434/api/chat",
        "frontend",
    ),
    Shape(
        "ollama native operation",
        "ollama/llama3",
        "http://localhost:11434/api/chat",
        "http://localhost:11434/api/chat",
        "frontend",
    ),
]
