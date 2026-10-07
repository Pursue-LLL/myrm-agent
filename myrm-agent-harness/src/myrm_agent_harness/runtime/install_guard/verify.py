"""Post-install harness verification for Docker, CI, and Tauri.

[INPUT]
- myrm_agent_harness.api::create_skill_agent (POS: Stable public agent factory)

[OUTPUT]
- run_verification(): Execute core-deps and public-API checks (+ optional CJK font check)
- verify_core_runtime_imports(): Probe lxml/dill/aiosqlite/bs4 from core dependencies
- main(): CLI entry for console script ``verify-harness-distribution``

[POS]
Production install gate. Confirms an installed harness wheel is importable and usable before Docker, CI, or Tauri release.
"""

from __future__ import annotations

import argparse
import sys


def verify_public_api() -> None:
    """Ensure the stable api surface resolves after production install."""
    from myrm_agent_harness.api import create_skill_agent

    if not callable(create_skill_agent):
        msg = "create_skill_agent is not callable via myrm_agent_harness.api"
        raise TypeError(msg)


def verify_core_runtime_imports() -> None:
    """Probe Tier-0/Tier-1 dependencies declared in pyproject core dependencies."""
    import aiosqlite  # noqa: F401
    import dill  # noqa: F401
    import lxml  # noqa: F401
    from bs4 import BeautifulSoup

    BeautifulSoup("<body>x</body>", "lxml")


def verify_matplotlib_cjk() -> None:
    """Fail-fast CJK font check for server runtime images (matches Dockerfile.official)."""
    import matplotlib

    matplotlib.use("Agg")
    from pathlib import Path

    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm

    font_dir = Path("/usr/share/fonts/opentype/noto")
    font_path = next(font_dir.glob("NotoSansCJK-Regular.ttc"))
    fm.fontManager.addfont(str(font_path))
    prop = fm.FontProperties(fname=str(font_path))
    resolved = fm.findfont(prop)
    if "NotoSansCJK" not in resolved:
        msg = f"CJK font not active: {resolved}"
        raise RuntimeError(msg)

    _fig, ax = plt.subplots()
    ax.set_title("中文渲染验证", fontproperties=prop)
    _fig.savefig("/tmp/_mpl_verify.png")
    print("matplotlib CJK verified:", resolved)


def run_verification(*, matplotlib_cjk: bool = False) -> None:
    """Run all post-install checks."""
    verify_core_runtime_imports()
    verify_public_api()
    print("harness install OK")
    if matplotlib_cjk:
        verify_matplotlib_cjk()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify production harness installation")
    parser.add_argument(
        "--matplotlib-cjk",
        action="store_true",
        help="Also verify matplotlib resolves Noto CJK (server Docker runtime)",
    )
    args = parser.parse_args()
    try:
        run_verification(matplotlib_cjk=args.matplotlib_cjk)
    except Exception as exc:
        print(f"harness install verification FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
