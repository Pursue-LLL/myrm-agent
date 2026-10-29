"""Per-file redaction of grep matches.

[INPUT]
- agent.security.redact::redact_file_text (POS: per-file redaction by file type)

[OUTPUT]
- redact_matches: the match list with each line redacted as its own file's text

[POS]
Redacts grep matches before they are formatted, so a line of code reads the same in grep as in file_read_tool (a
type name or a variable name that merely contains ``token`` is not masked in a source file).
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.redact import redact_file_text

type Match = dict[str, str | int]


def _redact_run(path: str, run: list[Match]) -> list[Match]:
    """Redact consecutive lines of one file together, so a secret spread over lines (a PEM block) is still seen.

    A multi-line secret is masked as a block shorter than its lines, so the redacted lines are padded with empty
    lines to the length of the run (and never split per line, which would show the secret).
    """
    lines = redact_file_text(path, "\n".join(str(m["content"]) for m in run)).split("\n")
    kept, overflow = lines[: len(run) - 1], lines[len(run) - 1 :]
    lines = [*kept, " ".join(overflow)]
    lines += [""] * (len(run) - len(lines))
    return [{**m, "content": line} for m, line in zip(run, lines, strict=True)]


def redact_matches(matches: list[Match]) -> list[Match]:
    """Return ``matches`` with every content line redacted by the type of the file it came from."""
    redacted: list[Match] = []
    run: list[Match] = []
    for match in matches:
        if run and (match["file"] != run[-1]["file"] or int(match["line"]) != int(run[-1]["line"]) + 1):
            redacted.extend(_redact_run(str(run[0]["file"]), run))
            run = []
        run.append(match)
    if run:
        redacted.extend(_redact_run(str(run[0]["file"]), run))
    return redacted
