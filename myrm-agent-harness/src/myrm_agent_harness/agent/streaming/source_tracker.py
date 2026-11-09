"""单次运行的引用源追踪器

[INPUT]
- utils.logger_utils::get_agent_logger (POS: Agent logger)
- utils.url_utils::url_dedup_key (POS: URL dedup key, display URL and domain extraction)

[OUTPUT]
- SourceTracker: 单次运行的引用源追踪（编号 + 去重 + 增量返回）；工具写给模型的编号就是卡片的 index；
  restore 接上同一线程此前写给模型的编号

[POS]
Source reference forwarding capability for BaseAgent.

"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.url_utils import url_dedup_key

logger = get_agent_logger(__name__)


class SourceTracker:
    """单次运行的引用源追踪器

    职责：
    - 编号：工具在拿到卡片之前就要把编号写进结果文本（index_for），卡片稍后才发出（add_batch）。
      同一来源在整次运行里只有一个编号，卡片的 index 就是模型读到的那个编号
    - 续号：同一线程的后一次运行（审批续跑、同线程的下一轮）用 restore 接上此前写给模型的编号，
      模型上下文里的一个编号只指向一个页面
    - 页面级去重（带 url 的来源按 url_dedup_key 去重：同一页面的不同拼写是一个来源，不同锚点是不同来源）
    - 内容级去重（无 url 的来源按全字段哈希去重）
    - 增量返回（add_batch 只返回本次新增的来源）

    工具接入方式：
    在工具返回值中包含 metadata.sources 字段即可：tool_interceptor_middleware 把它提升到
    ToolMessage.additional_kwargs，event_handlers 再交给 add_batch。要在结果文本里给来源编号的工具，
    通过 core.context_vars.source_indexer_var 取到 index_for，对每个来源（metadata.sources 里的同一个字典）取号。
    """

    def __init__(self) -> None:
        # 来源键 -> 写给模型的编号。工具取号时绑定一次，卡片发出时再绑定一次，
        # 所以无论哪个先发生，同一页面都是同一个编号。
        self._numbers: dict[str, int] = {}
        # 已经发出卡片的编号：一个编号只发一张卡片。
        self._numbers_with_card: set[int] = set()
        self._next_index = 1

    def index_for(self, source: Mapping[str, object]) -> int:
        """返回 source 的编号：去重键相同的来源编号相同，首次取号时发出；引文规范化改写过 URL 的来源按原链接认号。

        工具在写结果文本时调用，早于 add_batch 看到这个来源；传入的字段要与稍后交给 add_batch 的一致。
        """
        return self._number_for(source, self._dedup_key(source))

    def restore(self, stated: Sequence[Mapping[str, object]]) -> None:
        """接上同一线程此前写给模型的编号：``stated`` 是此前各次工具调用留下的来源，各带当时写给模型的 ``index``。

        这些来源沿用原编号（同一页面的几种拼写可以带同一个编号，各自都认它；一个页面带过两个编号时沿用先出现的），
        之后取号的新来源接在最大编号之后；没有可用编号的来源跳过。开跑时调用一次，早于任何 index_for。
        """
        for source in stated:
            number = source.get("index")
            if not isinstance(number, int) or isinstance(number, bool) or number < 1:
                continue
            self._next_index = max(self._next_index, number + 1)
            key = self._dedup_key(source)
            self._numbers.setdefault(self._numbered_key(source, key), number)
            self._numbers.setdefault(key, number)

    def add_batch(self, raw_sources: list[dict[str, object]]) -> list[dict[str, object]]:
        """添加一批来源，返回去重后的新增来源（index 是工具写给模型的编号，没取过号的来源取下一个空号）"""
        new_items: list[dict[str, object]] = []
        for src in raw_sources:
            if not isinstance(src, dict):
                continue
            key = self._dedup_key(src)
            number = self._number_for(src, key)
            if number in self._numbers_with_card:
                continue

            item = {**src, "index": number}
            if self._numbers.setdefault(key, number) != number:
                # 最终 URL 已经属于另一个编号。同一 URL 的两张卡片会在服务端和客户端被合并（二者都按 URL 认卡片），
                # 让一个已写给模型的编号没有卡片，所以这张卡片保留编号当时写给模型的 URL。
                item["url"] = item.pop("redirect_url")
            self._numbers_with_card.add(number)
            new_items.append(item)

        if new_items:
            logger.debug("SourceTracker: +%d new (total %d)", len(new_items), len(self._numbers_with_card))
        return new_items

    def _number_for(self, src: Mapping[str, object], own_key: str) -> int:
        """src 的编号：先认工具取号时用的键（改写前的 URL），没有再用 src 自己的键取号。"""
        number = self._numbers.get(self._numbered_key(src, own_key))
        return number if number is not None else self._number_of(own_key)

    def _number_of(self, key: str) -> int:
        number = self._numbers.get(key)
        if number is None:
            number = self._numbers[key] = self._next_index
            self._next_index += 1
        return number

    def _numbered_key(self, src: Mapping[str, object], own_key: str) -> str:
        """工具给 src 取号时用的键：引文规范化改写过 URL 时，是改写之前的 URL（redirect_url），否则就是 src 自己的键。"""
        redirect_url = src.get("redirect_url")
        if isinstance(redirect_url, str) and redirect_url:
            return self._dedup_key({**src, "url": redirect_url})
        return own_key

    def _dedup_key(self, src: Mapping[str, object]) -> str:
        """Generate dedup key (pure generic, no business field hardcoding beyond stable keys).

        Strategy:
        1. source_key → explicit stable key from tool metadata (preferred)
        2. url → same-page key (spellings of one page share it, anchors tell pages apart)
        3. otherwise → hash of all non-index fields
        """
        if source_key := src.get("source_key"):
            return f"source_key:{source_key}"
        url = src.get("url")
        if isinstance(url, str) and url:
            return f"url:{url_dedup_key(url, keep_fragment=True)}"
        stable = sorted((k, str(v)) for k, v in src.items() if k != "index")
        return f"content:{hash(tuple(stable))}"
