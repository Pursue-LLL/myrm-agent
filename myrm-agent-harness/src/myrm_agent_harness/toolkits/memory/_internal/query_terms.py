"""Query-side function-word pruning for the sparse BM25 mirror.

[INPUT]
- none (pure functions over an already tokenized query)

[OUTPUT]
- prune_function_words: drop closed-class and conversational filler tokens from a sentence-length tokenized query
- MIN_SENTENCE_TOKENS: the token count from which a query counts as a sentence

[POS]
Conversational queries ("what did I say about the release plan before",
"我之前跟你说过的关于发布计划的事情是怎么来着") carry far more function words than
content words. The mirror scores by weighted term overlap, so every filler token
that also occurs in stored memories adds score to unrelated hits. Only sentence-length
queries are pruned (``MIN_SENTENCE_TOKENS``); a short query is already a keyword query.
Pruning happens on the query side only: stored documents keep their full token stream, so no
mirror rewrite is needed. The legacy corpus-scroll path does not use this module;
it already selects long-query terms by corpus IDF, which the mirror client cannot
compute because the server owns the document statistics.

The lists are closed-class words plus a small set of conversational fillers
(say / remember / earlier ...) for English and Chinese. Negations (not, no, never,
不, 没有) are deliberately kept: they carry meaning, and their weight is already
bounded by the server-side IDF. Ambiguous homographs that are also common names or
nouns (will, may) are kept as well. Matching is exact on the tokenizer's lowercase
output, so an upper-case acronym token such as ``IT`` is never mistaken for the
pronoun ``it``.
"""

from __future__ import annotations

from typing import Final

_EN_FUNCTION_WORD_LIST: Final[str] = """
    a an the and or but if then than so as of at by for from in into on onto to up down out off over under
    with without about above after again against all am any are aren be because been before being below
    between both can could couldn did didn do does doesn doing don during each few further had hadn has hasn
    have haven having he her here hers herself him himself his how i is isn it its itself just let me more
    most my myself only other our ours ourselves own same she should shouldn some such that their theirs
    them themselves there these they this those through too until very was wasn we were weren what when where
    which while who whom why would wouldn you your yours yourself yourselves
    s t d ll m o re ve y
    also ever might must shall tell told said say says mention mentioned remember remind recall earlier
    previously ago please something anything everything someone anyone thing things
"""

_ZH_FUNCTION_WORD_LIST: Final[str] = """
    的 了 着 过 地 得 啊 呀 吗 呢 吧 嘛 哦 么 我 你 他 她 它 咱 您 们 是 在 有 和 跟 与 及 同 或 也 都 就
    才 又 再 还 很 太 更 把 被 给 对 从 向 往 为 以 之 而 但 并 所 个 这 那 哪 谁 几 来 去 说 讲 提 想 要 会
    能 可 让 帮 请
    之前 以前 之后 以后 刚才 刚刚 上次 这次 最近 曾经 已经 正在 一直 还是 或者 以及 如果 因为 所以 然后
    但是 可是 而且 关于 有关 对于 一下 一些 一个 一种 这个 那个 哪个 这些 那些 什么 怎么 怎样 如何
    为什么 为何 是否 有没有 多少 哪里 哪儿 这里 那里 请问 麻烦 帮忙 记得 回忆 想起 提到 提过 说过 聊到
    聊过 说起 事情 东西 来着 怎么回事 那件 那件事 哪一天 再说 具体 可以 能够 可能 应该 需要 比较 非常
    特别 有点 一点 我们 你们 他们 她们 咱们
"""

_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(_EN_FUNCTION_WORD_LIST.split()) | frozenset(
    _ZH_FUNCTION_WORD_LIST.split()
)


MIN_SENTENCE_TOKENS: Final[int] = 5


def prune_function_words(tokens: list[str]) -> list[str]:
    """Return ``tokens`` without function words, or ``tokens`` itself if nothing else is left.

    Only sentence-length queries are pruned: a short query is already a keyword
    query, every token chosen on purpose, and a function word in it ("between",
    "before") may be exactly the term that singles out the memory. A query made
    only of function words ("who are you") keeps its original tokens: an empty
    query would match nothing, while the unpruned one still ranks.
    """
    if len(tokens) < MIN_SENTENCE_TOKENS:
        return tokens
    content = [token for token in tokens if token not in _FUNCTION_WORDS]
    return content or tokens
