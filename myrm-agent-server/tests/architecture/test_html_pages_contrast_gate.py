"""Every module that writes a whole HTML page has a test that holds its colours to the WCAG contrast bar, or is listed with why not.

[INPUT]
- app/**/*.py: modules whose source holds an ``<!DOCTYPE html>`` or ``<html`` opening tag
- the contrast test registered for each page below

[OUTPUT]
- Fails when a module writes an HTML page and is neither registered with a contrast test nor listed as no page, when a
  registered test is missing or never calls a contrast check, or when a listed module no longer writes a page (so the
  lists cannot rot).

[POS]
tests/architecture/test_html_pages_contrast_gate.py: the pages the server hands to a browser (share links, hosting,
OAuth results, the welcome page, session exports) each draw their own stylesheet, so one that is added without a
contrast test would ship text a reader cannot read in one of the two themes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[2]
_APP = _SERVER / "app"

_OPENING_TAG = re.compile(r"<!doctype html|<html[\s>]", re.IGNORECASE)
# The calls of ``tests/support/wcag_contrast.py`` that compare two colours.
_CONTRAST_CHECKS = frozenset({"assert_readable", "assert_visible", "contrast"})

# page module -> the test that reads its stylesheet against WCAG 1.4.3 / 1.4.11.
_CHECKED_BY: dict[str, str] = {
    "app/api/integrations/oauth_result_page.py": "tests/api/integrations/test_oauth_result_page.py",
    "app/api/webui/welcome_page.py": "tests/api/webui/test_welcome_page.py",
    "app/core/security/share/share_password_page.py": "tests/core/security/test_share_page_contrast.py",
    "app/core/security/share/share_status_page.py": "tests/core/security/test_share_page_contrast.py",
    "app/services/chat/share_renderer.py": "tests/services/chat/test_chat_share_renderer_presentation.py",
    "app/services/hosting/decryptor_shell.py": "tests/services/hosting/test_decryptor_shell_contrast.py",
    "app/services/hosting/viewer_scaffold.py": "tests/services/hosting/test_viewer_scaffold_contrast.py",
    "app/services/session_export/interactive_html_compiler.py": "tests/services/session_export/test_interactive_html_compiler.py",
}

# Modules that mention an HTML tag without writing a page a browser shows.
_NOT_A_PAGE: dict[str, str] = {
    "app/api/chats/test_fixtures/wechat_draft.py": "article fragments fed to the draft compliance scanner; never served",
    "app/core/security/share/__init__.py": "its docstring names the <html lang> attribute; it writes no markup",
}


def _page_writers() -> set[str]:
    return {
        source.relative_to(_SERVER).as_posix()
        for source in _APP.rglob("*.py")
        if _OPENING_TAG.search(source.read_text(encoding="utf-8"))
    }


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def _calls_a_contrast_check(source: str) -> bool:
    return any(isinstance(node, ast.Call) and _called_name(node.func) in _CONTRAST_CHECKS for node in ast.walk(ast.parse(source)))


def test_every_module_that_writes_an_html_page_has_a_contrast_test_or_a_reason() -> None:
    unlisted = sorted(_page_writers() - _CHECKED_BY.keys() - _NOT_A_PAGE.keys())

    assert not unlisted, (
        f"{unlisted} write an HTML page. Test its text and control colours with tests/support/wcag_contrast.py "
        "and register the test in _CHECKED_BY, or list the module in _NOT_A_PAGE with the reason it shows no page."
    )


def test_a_listed_module_still_writes_a_page() -> None:
    stale = sorted((_CHECKED_BY.keys() | _NOT_A_PAGE.keys()) - _page_writers())

    assert not stale, f"{stale} no longer write an HTML page (or are gone); remove them from _CHECKED_BY / _NOT_A_PAGE."


def test_no_module_is_both_checked_and_listed_as_no_page() -> None:
    assert not _CHECKED_BY.keys() & _NOT_A_PAGE.keys()


def test_every_registered_contrast_test_exists_and_compares_colours() -> None:
    unproven = [
        test
        for test in sorted(set(_CHECKED_BY.values()))
        if not (_SERVER / test).is_file() or not _calls_a_contrast_check((_SERVER / test).read_text(encoding="utf-8"))
    ]

    assert not unproven, f"{unproven} are missing or never call assert_readable / assert_visible / contrast."


def test_the_page_detector_reads_opening_tags_and_not_prose() -> None:
    assert _OPENING_TAG.search('return f"""<!DOCTYPE html>')
    assert _OPENING_TAG.search('<html lang="en">')
    assert _OPENING_TAG.search("<HTML>")
    assert not _OPENING_TAG.search("the <htmlx> tag and a plain html word")
    assert not _OPENING_TAG.search("<head><title>fragment</title></head>")


def test_a_test_that_only_imports_the_helper_does_not_count_as_comparing_colours() -> None:
    assert _calls_a_contrast_check("assert_readable(page, 'light', 'p', '.card')")
    assert _calls_a_contrast_check("wcag_contrast.contrast('#000', '#fff')")
    assert not _calls_a_contrast_check("from tests.support.wcag_contrast import assert_readable\nx = assert_readable")
    assert not _calls_a_contrast_check("def test_page() -> None:\n    assert 'color' in page")
