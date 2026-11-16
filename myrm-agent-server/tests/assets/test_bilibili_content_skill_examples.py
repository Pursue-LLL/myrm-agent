"""The Bilibili skill's example queries are the ones the engine answers from the Bilibili API.

[INPUT]
- assets/prebuilt_skills/bilibili-content/SKILL.md: the "Finding Videos" list the agent copies its search queries from
- myrm_agent_harness.toolkits.web_search.providers.bilibili_search::is_bilibili_video_query (POS: the predicate ``engine`` applies to every question of a call)

[OUTPUT]
- (tests only)

[POS]
``engine`` runs the Bilibili video search only when every question of a call is scoped to Bilibili videos; one question
without a ``site:bilibili.com`` operator sends the whole call to the general providers. The skill's examples are what an
agent copies, so each of them has to meet that condition. The predicate lives in the harness and the examples in this
package's assets, so nothing else ties them together.
"""

from __future__ import annotations

import re
from pathlib import Path

from myrm_agent_harness.toolkits.web_search.providers.bilibili_search import is_bilibili_video_query

_SKILL = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "bilibili-content" / "SKILL.md"
_BV_ID = re.compile(r"BV\w{10}")


def _example_queries() -> list[str]:
    """Code spans of the list under "### Finding Videos"; a BV number is a lookup key, not a search query."""
    section = _SKILL.read_text(encoding="utf-8").split("### Finding Videos", 1)[1].split("\n###", 1)[0]
    spans = [span for line in section.splitlines() if line.startswith("- ") for span in re.findall(r"`([^`]+)`", line)]
    return [span for span in spans if not _BV_ID.search(span)]


def test_every_example_query_is_scoped_to_bilibili_videos() -> None:
    examples = _example_queries()
    assert len(examples) >= 2, "the section lost its example queries, so the check below would pass on nothing"
    unscoped = [query for query in examples if not is_bilibili_video_query(query)]
    assert not unscoped, f"a call copied from these examples skips the Bilibili video search: {unscoped}"
