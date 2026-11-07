"""[INPUT]
- fastapi.APIRouter (POS: 路由容器)

[OUTPUT]
- router / logger

[POS]
The statistics APIRouter shared by the endpoint modules; sub-routers are mounted here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

router = APIRouter()


logger = logging.getLogger(__name__)
