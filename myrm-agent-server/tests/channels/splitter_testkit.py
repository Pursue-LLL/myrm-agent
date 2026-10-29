"""Document builders and checks shared by the splitter limit tests."""

from __future__ import annotations

import random
import re

FENCE_LINE = re.compile(r"^(`{3,10}|~{3,10})\w*\s*$")
EMPTY_FENCE = re.compile(r"^(`{3,10}|~{3,10})\w*\s*\1$")

LATIN_WORDS = ("alpha", "beta", "gamma,", "delta.")
CJK_WORDS = ("你好", "世界，", "测试内容。", "😀")


def text_of(chunks: list[str]) -> str:
    """The words of the chunks without fence marker lines and whitespace: what a reader would see of the reply."""
    kept = [line for chunk in chunks for line in chunk.split("\n") if not FENCE_LINE.match(line.strip())]
    return re.sub(r"\s+", "", "".join(kept))


def random_document(rng: random.Random, limit: int, *, words: tuple[str, ...] = LATIN_WORDS, code_char: str = "c") -> str:
    """Prose and fenced code whose lines run up to more than two chunks long, so every split path is reached."""
    blocks: list[str] = []
    for _ in range(rng.randint(2, 8)):
        if rng.random() < 0.5:
            blocks.append(" ".join(rng.choice(words) for _ in range(rng.randint(1, limit // 2))))
            continue
        opening, closing = rng.choice([("```", "```"), ("```python", "```"), ("~~~", "~~~"), ("````", "````")])
        lines = [code_char * rng.randint(1, limit * 2) for _ in range(rng.randint(1, 6))]
        blocks.append("\n".join([opening, *lines, closing]))
    return "\n".join(blocks)
