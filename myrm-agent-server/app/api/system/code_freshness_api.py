"""
[INPUT]: Runtime code inspection queries, custom module descriptors, and path verification requests.
[OUTPUT]: REST API endpoints reporting three-state code freshness (fresh/stale/indeterminate) and drain/restart recommendations.
[POS]: myrm-agent/myrm-agent-server/app/api/system/code_freshness_api.py
"""

import os
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.code_freshness import (
    FreshnessState,
    IndeterminateReason,
    ModuleFreshnessEntry,
    RuntimeCodeFreshnessInspector,
    RuntimeFreshnessReport,
)

router = APIRouter(prefix="/code-freshness", tags=["code-freshness"])

_default_inspector = RuntimeCodeFreshnessInspector()
# Pre-register current server entrypoints
_server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_main_py = os.path.join(_server_dir, "main.py")
if os.path.exists(_main_py):
    _default_inspector.register_module("server.main", _main_py)


def get_default_code_freshness_inspector() -> RuntimeCodeFreshnessInspector:
    return _default_inspector


# --- Request/Response Models ---


class InspectModuleRequest(BaseModel):
    module_name: str = Field(..., description="Logical module name")
    file_path: str = Field(..., description="Filesystem absolute path")
    mock_mtime_ms: Optional[int] = Field(default=None, description="Optional mocked mtime for validation")


class RegisterModuleRequest(BaseModel):
    module_name: str = Field(..., description="Module identifier")
    file_path: str = Field(..., description="Source code file path")


# --- Endpoints ---


@router.get("/report")
def get_runtime_freshness_report() -> Dict[str, object]:
    """Retrieve runtime-wide code freshness audit comparing active process lifetime against on-disk code."""
    inspector = get_default_code_freshness_inspector()
    report: RuntimeFreshnessReport = inspector.inspect_runtime()
    return report.model_dump()


@router.post("/inspect-module")
def inspect_module(req: InspectModuleRequest) -> Dict[str, object]:
    """Perform ad-hoc three-state code freshness inspection on a specific script or module."""
    inspector = get_default_code_freshness_inspector()
    entry: ModuleFreshnessEntry = inspector.inspect_file(
        module_name=req.module_name,
        file_path=req.file_path,
        mock_mtime_ms=req.mock_mtime_ms,
    )
    return entry.model_dump()


@router.post("/register")
def register_module(req: RegisterModuleRequest) -> Dict[str, str]:
    """Register an additional entrypoint file path into the recurring freshness audit roster."""
    inspector = get_default_code_freshness_inspector()
    inspector.register_module(req.module_name, req.file_path)
    return {"status": "registered", "module_name": req.module_name, "file_path": req.file_path}


@router.post("/reset")
def reset_inspector() -> Dict[str, str]:
    """Reset registered modules and anchor timestamp for test isolation."""
    global _default_inspector
    _default_inspector = RuntimeCodeFreshnessInspector()
    return {"status": "reset"}
