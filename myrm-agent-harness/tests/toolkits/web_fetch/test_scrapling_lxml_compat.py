"""scrapling parsing must not trip the suite-wide ``filterwarnings = error`` gate.

scrapling hands ``strip_cdata`` to lxml's ``HTMLParser``; lxml reports that as a ``DeprecationWarning``. The pytest
config ignores that single message, so every fetcher built on scrapling keeps working under the warning gate.
"""

from __future__ import annotations

from scrapling.parser import Selector


def test_scrapling_selector_parses_html_under_warning_gate() -> None:
    page = Selector("<html><body><p>hello</p></body></html>")

    assert page.css("p::text").get() == "hello"
