"""Decides whether a request needs fresh data from outside the run (news, prices, weather, releases).

The word "latest" settles it on its own; the weaker time words (today, current, live, now, ...) matter only
beside a topic that changes (news, a price, a score, a release) or an explicit ask to look it up. A topic that
changes by nature (the weather, an exchange rate, a score) needs no time word. A request that is about the user's
own project or material, or only transforms text it was given (translate, proofread), never needs the web unless
it asks for it. Without that, a time word in a sentence about anything else ("current month's orders", "live
migration", "translate: nice weather today") would hold the answer to evidence no tool could give it.

A short question about this very day or moment ("is the bridge closed right now?") is a lookup even when it names no
changing topic, unless it asks for advice; a long message is pasted material and never read that way.

The rule is a set of word lists, not a classifier: it is deterministic, costs no model call, and is pinned by a
labeled prompt set (``tests/agent/middlewares/completion/test_completion_guard_freshness.py``). The lists cover
English, Simplified Chinese and Traditional Chinese; a request in another language is not recognised.

[INPUT]
- (none)

[OUTPUT]
- demands_external_evidence(): whether the request needs fresh external data

[POS]
The trigger of the external-evidence gate. ``completion_guard_external_evidence`` decides whether the run's tool
records satisfy the demand; this module decides whether there is a demand.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


def _pattern(words: Iterable[str]) -> re.Pattern[str]:
    """One alternation over ``words``: whole-word for plain ASCII words, substring for everything else."""
    parts = [rf"\b{re.escape(word)}\b" if word.isascii() and word.isalpha() else re.escape(word) for word in words]
    return re.compile("|".join(parts))


# Settle it alone: the user asks for the newest state of something, wherever it lives.
_STRONG_CUES = _pattern(("latest", "newest", "most recent", "breaking", "最新", "刚刚", "剛剛"))

# Time words that say little alone ("today I feel tired", "live migration"): they count beside a changing topic.
_TIME_CUES = _pattern(
    (
        "today",
        "current",
        "currently",
        "now",
        "right now",
        "recent",
        "recently",
        "real-time",
        "realtime",
        "live",
        "this week",
        "this weekend",
        "this month",
        "this year",
        "tonight",
        "yesterday",
        "last night",
        "今天",
        "今日",
        "当前",
        "目前",
        "现在",
        "实时",
        "最近",
        "近期",
        "近日",
        "这两天",
        "这几天",
        "本周",
        "本月",
        "今年",
        "今晚",
        "昨天",
        "昨晚",
        "當前",
        "現在",
        "實時",
        "這兩天",
        "這幾天",
        "本週",
    )
)

# What changes under the user's feet; useless without a time word ("price elasticity", "stock photo").
_CHANGING_TOPICS = _pattern(
    (
        "news",
        "price",
        "prices",
        "stock",
        "stocks",
        "score",
        "release",
        "version",
        "ranking",
        "standings",
        "leaderboard",
        "trending",
        "outage",
        "nasdaq",
        "新闻",
        "价格",
        "股票",
        "行情",
        "比分",
        "票房",
        "发布",
        "版本",
        "排名",
        "排行",
        "热门",
        "热搜",
        "动态",
        "报道",
        "美股",
        "港股",
        "收盘",
        "市值",
        "纳指",
        "多少钱",
        "赛程",
        "新聞",
        "價格",
        "發佈",
        "動態",
        "報導",
        "收盤",
        "納指",
        "多少錢",
        "賽程",
        "熱門",
        "熱搜",
    )
)

# Changes by nature: asking for it is asking for the present value, with or without a time word.
_VOLATILE_FACTS = _pattern(
    (
        "weather",
        "forecast",
        "exchange rate",
        "stock price",
        "box office",
        "天气",
        "天氣",
        "汇率",
        "匯率",
        "股价",
        "股價",
        "比分",
        "票房",
    )
)

# Asks the run to look something up or to show where it came from.
_CITATION_CUES = _pattern(
    (
        "source",
        "sources",
        "citation",
        "citations",
        "reference",
        "references",
        "来源",
        "來源",
        "出处",
        "出處",
        "链接",
        "連結",
        "官网",
        "官網",
    )
)
_WEB_CUES = _pattern(
    ("web", "internet", "online", "search", "website", "网址", "网页", "網頁", "网站", "搜索", "搜尋", "联网", "聯網")
)

# The "latest" of the user's own project or material is theirs to read, not the web's to answer.
_OWN_WORK_CUES = _pattern(
    (
        "代码",
        "项目",
        "文件",
        "仓库",
        "提交",
        "模块",
        "接口",
        "改动",
        "重构",
        "函数",
        "逻辑",
        "分支",
        "测试",
        "脚本",
        "日志",
        "报错",
        "编译",
        "部署",
        "配置",
        "code",
        "project",
        "file",
        "repo",
        "repository",
        "git",
        "commit",
        "module",
        "interface",
        "refactor",
        "function",
        "logic",
        "branch",
        "test",
        "tests",
        "testing",
        "script",
        "scripts",
        "log",
        "logs",
        "bug",
        "csv",
        "excel",
        "xlsx",
        "spreadsheet",
        "attached",
        "attachment",
        "表格",
        "附件",
        "文档",
        "代碼",
        "專案",
        "倉庫",
        "模組",
        "介面",
        "重構",
        "函式",
        "邏輯",
        "測試",
        "腳本",
        "日誌",
        "報錯",
        "編譯",
        "文檔",
    )
)

# The text to work on is in the request; nothing in it is asked of the outside world.
_TEXT_TRANSFORMS = _pattern(
    (
        "translate",
        "translation",
        "proofread",
        "paraphrase",
        "rewrite",
        "翻译",
        "翻譯",
        "润色",
        "潤色",
        "改写",
        "改寫",
        "校对",
        "校對",
        "纠错",
        "糾錯",
    )
)

# A short question about this very day or moment is a lookup even when it names no changing topic ("what's the score
# tonight?", "is the bridge closed right now?").
_MOMENT_CUES = _pattern(
    (
        "today",
        "tonight",
        "right now",
        "last night",
        "yesterday",
        "this week",
        "this weekend",
        "今天",
        "今晚",
        "本周",
        "这周",
        "本週",
        "這週",
        "昨天",
        "昨晚",
        "现在",
        "現在",
        "刚刚",
        "剛剛",
    )
)
_QUESTION_FORM = re.compile(
    r"\?|？|^(?:is|are|does|do|did|will|can|has|have)\b|\b(?:what|how|when|where|who|which)\b"
    r"|吗|嗎|什么|什麼|怎么|怎麼|怎样|怎樣|几点|幾點|哪|是否|有没有|有沒有|多少|如何"
)
# Asks for a view or a plan for the user, not for a fact about the world.
_ADVICE_ASKS = re.compile(
    r"\b(?:should i|shall i|can i)\b|\bany tips\b|我(?:现在|現在|今天)?(?:应该|應該|该|該|想)|要不要|应该先|應該先"
    r"|有什么.{0,4}建议|有什麼.{0,4}建議|入门建议|入門建議"
)
# A question is short. Pasted material (a contract, a log, a listing) carries its own "today" and its own question
# marks, and holding the answer about it to web evidence would be wrong.
_MOMENT_QUESTION_MAX_CHARS = 200


def _asks_about_the_moment(text: str) -> bool:
    return (
        len(text) <= _MOMENT_QUESTION_MAX_CHARS
        and _MOMENT_CUES.search(text) is not None
        and _QUESTION_FORM.search(text) is not None
        and _ADVICE_ASKS.search(text) is None
    )


def demands_external_evidence(request: str) -> bool:
    """Whether answering ``request`` well needs fresh data from outside the run."""
    text = request.lower()
    cites = _CITATION_CUES.search(text) is not None
    web = _WEB_CUES.search(text) is not None
    if cites and web:
        return True
    asks_to_look_up = cites or web
    own_work = _OWN_WORK_CUES.search(text) is not None
    if _STRONG_CUES.search(text):
        return asks_to_look_up or not own_work
    if (own_work or _TEXT_TRANSFORMS.search(text)) and not asks_to_look_up:
        return False
    if _VOLATILE_FACTS.search(text):
        return True
    if _TIME_CUES.search(text) is not None and (asks_to_look_up or _CHANGING_TOPICS.search(text) is not None):
        return True
    return _asks_about_the_moment(text)


__all__ = ["demands_external_evidence"]
