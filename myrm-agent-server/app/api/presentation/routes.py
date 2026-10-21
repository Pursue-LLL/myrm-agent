"""
[INPUT]
- PresentationGenerateRequest, PresentationArtifactResponse, SlideData from app.api.presentation.models
- generate_presentation_structure, render_pptx_binary from app.api.presentation.pptx_generator

[OUTPUT]
- APIRouter exposing:
  - POST /api/v1/presentation/generate (generate structured slides and pptx binary)
  - GET /api/v1/presentation/{id} (query generated presentation metadata and slides)
  - GET /api/v1/presentation/{id}/download (stream binary pptx download)

[POS]
FastAPI route layer for EnterprisePresentationSlideGeneratorAndVisualConceptIllustrator.
Single file < 150 lines. Strictly typed.
"""

import io
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Dict, Tuple

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.presentation.models import (
    PresentationArtifactResponse,
    PresentationGenerateRequest,
)
from app.api.presentation.pptx_generator import (
    generate_presentation_structure,
    render_pptx_binary,
)

router = APIRouter()

# In-memory artifact store for generated presentations: {id: (metadata, pptx_bytes)}
_PRESENTATION_STORE: Dict[str, Tuple[PresentationArtifactResponse, bytes]] = {}


@router.post("/generate", response_model=PresentationArtifactResponse, status_code=status.HTTP_201_CREATED)
async def generate_presentation(
    request: PresentationGenerateRequest,
) -> PresentationArtifactResponse:
    artifact_id = f"pres_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    slides = generate_presentation_structure(request)
    pptx_bytes = render_pptx_binary(slides, request.template_style, request.topic)

    file_name = f"{request.topic.replace(' ', '_')[:30]}_{request.template_style}.pptx"
    download_url = f"/api/v1/presentation/{artifact_id}/download"

    artifact = PresentationArtifactResponse(
        id=artifact_id,
        topic=request.topic,
        template_style=request.template_style,
        total_slides=len(slides),
        slides=slides,
        file_name=file_name,
        file_size_bytes=len(pptx_bytes),
        download_url=download_url,
        created_at=now_iso,
    )

    _PRESENTATION_STORE[artifact_id] = (artifact, pptx_bytes)
    return artifact


@router.get("/{presentation_id}", response_model=PresentationArtifactResponse)
async def get_presentation(presentation_id: str) -> PresentationArtifactResponse:
    if presentation_id not in _PRESENTATION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Presentation artifact {presentation_id} not found",
        )
    artifact, _ = _PRESENTATION_STORE[presentation_id]
    return artifact


@router.get("/{presentation_id}/download")
async def download_presentation_pptx(presentation_id: str) -> StreamingResponse:
    if presentation_id not in _PRESENTATION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Presentation artifact {presentation_id} not found",
        )
    artifact, pptx_bytes = _PRESENTATION_STORE[presentation_id]

    stream = io.BytesIO(pptx_bytes)
    safe_ascii_name = f"presentation_{presentation_id}.pptx"
    encoded_name = urllib.parse.quote(artifact.file_name)
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_ascii_name}"; filename*=UTF-8\'\'{encoded_name}',
    }
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers,
    )
