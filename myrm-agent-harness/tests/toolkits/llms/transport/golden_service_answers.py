"""Canned provider answers for the embedding, rerank, image and web-search golden matrix.

[INPUT]
- httpx (POS: request and response types)

[OUTPUT]
- Answerer: turns a recorded request into a valid provider answer, or an error status when a scenario asks for one

[POS]
Library-agnostic fake of the provider side. The answer is chosen by the endpoint the request addresses and sized by
what the request asked for (number of inputs, ``top_n``, ``n``), so the previous client library and the transport
both receive a well-formed answer for whatever URL they chose. Every answer carries the fields of all the provider
dialects it can be read as: a client picks the fields of its own provider and ignores the rest.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx

# 1x1 transparent PNG
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _vector(index: int) -> list[float]:
    return [0.1 * (index + 1), 0.2, 0.3]


def _body(request: httpx.Request) -> Mapping[str, object]:
    try:
        parsed = json.loads(request.content or b"{}")
    except (ValueError, httpx.RequestNotRead):
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _count(body: Mapping[str, object]) -> int:
    """How many inputs an embedding request carries, in any provider's field name."""
    for key in ("input", "texts", "inputs"):
        value = body.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, str):
            return 1
    requests = body.get("requests")
    return len(requests) if isinstance(requests, list) else 1


def _embedding(path: str, body: Mapping[str, object]) -> object:
    n = _count(body)
    vectors = [_vector(i) for i in range(n)]
    if path.endswith(":batchEmbedContents"):
        return {"embeddings": [{"values": v} for v in vectors]}
    if path.endswith(":embedContent"):
        return {"embedding": {"values": vectors[0]}}
    if path.endswith("/api/embed"):
        return {"model": "m", "embeddings": vectors, "total_duration": 1, "load_duration": 1, "prompt_eval_count": 1}
    if path.endswith("/api/embeddings"):
        return {"embedding": vectors[0]}
    if path.endswith("/v2/embed"):
        return {"id": "e", "embeddings": {"float": vectors}, "texts": ["t"] * n, "meta": {"api_version": {}}}
    if path.endswith("/v1/embed"):
        return {"id": "e", "embeddings": vectors, "texts": ["t"] * n, "response_type": "embeddings_floats"}
    return {
        "object": "list",
        "model": "m",
        "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


def _rerank(body: Mapping[str, object]) -> object:
    documents = body.get("documents")
    total = len(documents) if isinstance(documents, list) else 1
    wanted = body.get("top_n", body.get("top_k", total))
    count = min(wanted, total) if isinstance(wanted, int) else total
    rows = [{"index": i, "relevance_score": round(0.9 - 0.1 * i, 3)} for i in range(count)]
    return {
        "id": "r",
        "model": "m",
        "results": [{**row, "document": {"text": f"doc{row['index']}"}} for row in rows],
        "data": rows,
        "meta": {"billed_units": {"search_units": 1}},
        "usage": {"total_tokens": 1},
    }


def _image(path: str, body: Mapping[str, object]) -> object:
    n = body.get("n")
    count = n if isinstance(n, int) and n > 0 else 1
    if path.endswith("/v1/image_generation"):
        return {"data": {"image_base64": [PNG_B64] * count}, "base_resp": {"status_code": 0, "status_msg": "success"}}
    if ":predict" in path:
        return {"predictions": [{"bytesBase64Encoded": PNG_B64, "mimeType": "image/png"}] * count}
    if "/stable-image/" in path:
        return {"image": PNG_B64, "finish_reason": "SUCCESS", "seed": 1}
    if "/generation/" in path:
        return {"artifacts": [{"base64": PNG_B64, "seed": 1, "finishReason": "SUCCESS"}] * count}
    return {"created": 1, "data": [{"b64_json": PNG_B64, "revised_prompt": "rp"}] * count}


def _search() -> object:
    rows = [
        {
            "title": f"T{i}",
            "url": f"https://example.com/{i}",
            "link": f"https://example.com/{i}",
            "snippet": f"S{i}",
            "content": f"S{i}",
            "text": f"S{i}",
            "description": f"S{i}",
            "excerpts": [f"S{i}"],
            "date": "2024-01-0" + str(i + 1),
            "publishedDate": "2024-01-0" + str(i + 1),
            "publish_date": "2024-01-0" + str(i + 1),
            "type": "organic",
        }
        for i in range(2)
    ]
    return {
        "success": True,
        "results": rows,
        "items": rows,
        "organic": rows,
        "web": {"results": rows},
        "data": {"web": rows, "news": []},
        "tasks": [{"status_code": 20000, "result": [{"items": rows}]}],
    }


class Answerer:
    """Answers a recorded request; ``status`` other than 200 makes every answer that error."""

    def __init__(self) -> None:
        self.status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "golden failure"}}, request=request)
        split = urlsplit(str(request.url))
        path, body = split.path, _body(request)
        if "rerank" in path:
            answer = _rerank(body)
        elif "embed" in path:
            answer = _embedding(path, body)
        elif "image" in path or ":predict" in path or "/generation/" in path:
            answer = _image(path, body if body else _multipart_fields(request))
        else:
            answer = _search()
        return httpx.Response(200, json=answer, request=request)


def _multipart_fields(request: httpx.Request) -> Mapping[str, object]:
    """The ``n`` field of a multipart image edit, the only one an answer depends on."""
    text = (request.content or b"").decode("latin-1", "ignore")
    marker = 'name="n"\r\n\r\n'
    if marker not in text:
        return {}
    value = text.split(marker, 1)[1].split("\r\n", 1)[0]
    return {"n": int(value)} if value.isdigit() else {}
