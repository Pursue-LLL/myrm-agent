"""The hint a failed execution carries: what to try next, from its error category and the text of the error.

[INPUT]
- executors.models::ExecutionResult (POS: Data models for code execution; type only)

[OUTPUT]
- generate_error_hint: The actionable fix hint of a failed execution, or ``None`` when its category offers none

[POS]
Hint half of the error analysis of ``ExecutionResult``: ``models.py`` classifies the failure into a category, this module turns the category and the error text into the next step for the model.
"""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionResult

_MODULE_NAME_RE = re.compile(r"No module named ['\"]?([a-zA-Z0-9_]+)")
_COMMAND_NOT_FOUND_RE = re.compile(r"(\S+): (?:command not found|not found)")
_PERMISSION_PATH_RE = re.compile(r"Permission denied[:\s]+['\"]?([^\s'\"]+)")
_PROTECTED_GIT_RE = re.compile(r"\.git/(?:config|hooks)\b")

_IMPORT_TO_PYPI: dict[str, str] = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "attr": "attrs",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "gi": "PyGObject",
    "wx": "wxPython",
    "serial": "pyserial",
    "usb": "pyusb",
    "Crypto": "pycryptodome",
    "jwt": "PyJWT",
    "magic": "python-magic",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "fitz": "PyMuPDF",
    "telegram": "python-telegram-bot",
    "lark": "lark-parser",
}


def _get_preferred_pip_installer() -> str:
    """Return ``uv pip`` if uv is on PATH, otherwise ``pip``."""
    return "uv pip" if shutil.which("uv") else "pip"


def generate_error_hint(result: ExecutionResult) -> str | None:
    """Generate an actionable fix hint based on error_category and stderr."""
    category = result.error_category
    if not category or category in {"syntax", "unknown"}:
        return None

    combined = " ".join(filter(None, [result.error, result.stderr]))

    if category == "import":
        match = _MODULE_NAME_RE.search(combined)
        if match:
            module = match.group(1)
            pypi_name = _IMPORT_TO_PYPI.get(module, module)
            installer = _get_preferred_pip_installer()
            return f"Try: {installer} install {pypi_name}"
        return "A Python module is missing. Install it with pip install <module_name>."

    if category == "not_found":
        match = _COMMAND_NOT_FOUND_RE.search(combined)
        if match:
            return f"Command '{match.group(1)}' not found. Install it or check the PATH."
        return "A command was not found. Verify spelling and PATH."

    if category in {"permission_denied", "sandbox_ro"} and _PROTECTED_GIT_RE.search(combined):
        return (
            "[SYSTEM_ENFORCED] This repository's .git/config and .git/hooks are read-only in the sandbox. "
            "Do NOT retry or look for a way around it; ask the user to run that command themselves."
        )

    if category == "permission_denied":
        match = _PERMISSION_PATH_RE.search(combined)
        if match:
            path = match.group(1)
            return f"Try: chmod +x {path}"
        return "Permission denied. Check file permissions with ls -la and use chmod."

    if category == "sandbox_ro":
        return "[SYSTEM_ENFORCED] Current mount is read-only. You MUST write output to the /workspace directory."

    if category == "network_blocked":
        return (
            "[SYSTEM_ENFORCED] Network access is strictly blocked in this sandbox. "
            "Do NOT retry with different HTTP libraries (urllib, requests, curl, etc). "
            "Change your approach (e.g. generate mock data or ask the user)."
        )

    if category == "timeout":
        return "Execution timed out. Try reducing input size, splitting into smaller tasks, or increasing the timeout."

    if category == "oom":
        return "Out of memory. Try processing data in smaller chunks or reducing memory usage."

    return None


__all__ = ["generate_error_hint"]
