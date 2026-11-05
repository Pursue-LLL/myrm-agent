"""DOM-tree pruning content filter for fetched HTML.

Scores every node by text density, link density, tag weight, class/id hints and text length, drops the nodes below a
threshold and removes navigation, ads and other boilerplate. A ``header`` inside a content region is kept.

[INPUT]
utils.tree_truncator::truncate_html_soup (POS: Budget-aware truncation of HTML and ARIA trees) [lazy]

[OUTPUT]
ContentPruningFilter: Reduces a page to its main-content HTML blocks (``filter_content``)

[POS]
Boilerplate and noise pruning for the web fetch processing pipeline: turns raw page HTML into the content blocks
the Markdown generator converts.
"""

from __future__ import annotations

import logging
import math
import re
from collections import deque
from typing import cast

from bs4 import BeautifulSoup, Comment, Tag

logger = logging.getLogger(__name__)

_NEGATIVE_PATTERNS = re.compile(r"nav|footer|header|sidebar|ads|comment|promo|advert|social|share", re.I)

_EXCLUDED_TAGS = frozenset(
    {
        "nav",
        "footer",
        "aside",
        "script",
        "style",
        "form",
        "iframe",
        "noscript",
    }
)

_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "path",
        "link",
    }
)

# Scoring walks the ancestors of every element and re-reads each subtree's text, so its cost follows the number of
# ancestor-descendant pairs (the sum of all element depths), not the page size. Real pages stay well below this limit;
# a page far above it is a nesting bomb that would hold the conversion thread for minutes.
_MAX_SCORING_PATH_UNITS = 600_000


def _dom_path_units(root: Tag, limit: int) -> int:
    """Count the ancestor-descendant element pairs below *root* (the sum of every element's depth).

    Counts iteratively and stops once above *limit*, so measuring a pathologically deep page is cheap itself.
    """
    total = 0
    stack: list[tuple[Tag, int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        for child in node.children:
            if isinstance(child, Tag):
                total += depth + 1
                if total > limit:
                    return total
                stack.append((child, depth + 1))
    return total


class ContentPruningFilter:
    """Prunes a page's DOM tree down to its main content.

    1. Keeps ``article`` / ``main`` / ``section`` and a ``header`` inside them.
    2. Scores link density in context: a pure link list is boilerplate, a link-heavy paragraph is not.
    3. Weights emphasis tags such as ``strong`` and ``b`` higher.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.48,
        min_word_threshold: int = 0,
        metric_weights: dict[str, float] | None = None,
    ):
        self.threshold = threshold
        self.min_word_threshold = min_word_threshold

        self.excluded_tags: set[str] = set(_EXCLUDED_TAGS)

        self.metric_config = {
            "text_density": True,
            "link_density": True,
            "tag_weight": True,
            "class_id_weight": True,
            "text_length": True,
        }

        self.metric_weights: dict[str, float] = {
            "text_density": 0.4,
            "link_density": 0.2,
            "tag_weight": 0.2,
            "class_id_weight": 0.1,
            "text_length": 0.1,
        }
        if metric_weights:
            self.metric_weights.update(metric_weights)

        self.tag_weights: dict[str, float] = {
            "div": 0.5,
            "span": 0.5,
            "p": 1.1,
            "li": 0.5,
            "ul": 0.5,
            "ol": 0.5,
            "h1": 1.2,
            "h2": 1.1,
            "h3": 1.0,
            "h4": 0.9,
            "h5": 0.8,
            "h6": 0.7,
            "strong": 0.7,
            "b": 0.7,
            "body": 0.9,
            "section": 1.5,
            "main": 1.5,
            "article": 1.5,
        }

    # ------------------------------------------------------------------
    # DOM tree pruning
    # ------------------------------------------------------------------

    def _remove_comments(self, soup: BeautifulSoup) -> None:
        for element in soup(string=lambda text: isinstance(text, Comment)):
            element.extract()

    def _remove_unwanted_tags(self, soup: BeautifulSoup) -> None:
        for tag in self.excluded_tags:
            for element in soup.find_all(tag):
                element.decompose()

    def _prune_tree(self, node: Tag) -> None:
        text_len = len(node.get_text(strip=True))
        tag_len = len(node.encode_contents().decode("utf-8"))
        link_text_len = sum(len(s.strip()) for s in (a.string for a in node.find_all("a", recursive=False)) if s)

        metrics = {
            "node": node,
            "tag_name": node.name,
            "text_len": text_len,
            "tag_len": tag_len,
            "link_text_len": link_text_len,
        }

        score = self._compute_composite_score(metrics, text_len, tag_len, link_text_len)

        if score < self.threshold:
            node.decompose()
        else:
            for child in [child for child in node.children if isinstance(child, Tag)]:
                self._prune_tree(child)

    def _compute_class_id_weight(self, node: Tag) -> float:
        class_id_score = 0.0
        attrs = node.attrs
        if "class" in attrs:
            classes = " ".join(attrs["class"])
            if _NEGATIVE_PATTERNS.match(classes):
                class_id_score -= 0.5
        if "id" in attrs and _NEGATIVE_PATTERNS.match(str(attrs["id"])):
            class_id_score -= 0.5
        return class_id_score

    # ------------------------------------------------------------------
    # Region detection
    # ------------------------------------------------------------------

    def _check_element_area(self, element: Tag) -> str:
        node: Tag | None = element
        while node is not None:
            if node.name in {"main", "article", "section"}:
                return "content"
            if node.name in {"nav", "footer", "aside"}:
                return "navigation"
            node = node.parent
        return ""

    def _check_in_content_area(self, element: Tag) -> bool:
        return self._check_element_area(element) == "content"

    # ------------------------------------------------------------------
    # Helper checks
    # ------------------------------------------------------------------

    def _is_pure_link_list(self, node: Tag) -> bool:
        children_with_links = 0
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            if child.name == "a":
                children_with_links += 1
            else:
                try:
                    if child.find("a", recursive=True):
                        children_with_links += 1
                except (TypeError, AttributeError):
                    pass
        return children_with_links >= 2

    def _has_hidden_class(self, class_list: list[str]) -> bool:
        classes_str = " ".join(str(cls) for cls in class_list)
        return " hidden " in f" {classes_str} " or "hidden-" in classes_str or ":hidden" in classes_str

    def _has_ssr_variant_class(self, class_list: list[str]) -> bool:
        return any("ssr-variant" in str(cls) for cls in class_list)

    def _bfs_find_content_section(self, element: Tag) -> bool:
        queue: deque[Tag] = deque([element])
        visited: set[int] = {id(element)}
        while queue:
            current = queue.popleft()
            if current.name in ("section", "main", "article"):
                return True
            for child in current.children:
                if isinstance(child, Tag) and id(child) not in visited:
                    queue.append(child)
                    visited.add(id(child))
        return False

    def _compute_content_hash(self, element: Tag) -> int | None:
        text = element.get_text(strip=True)
        if not text or len(text) < 10:
            return None
        return hash(f"{element.name}:{len(list(element.children))}:{text[:300]}")

    # ------------------------------------------------------------------
    # Core filter
    # ------------------------------------------------------------------

    def filter_content(self, html: str, max_chars: int = 0) -> tuple[list[str], bool]:
        """Prune *html* to its content blocks (outer HTML strings) and report whether they were truncated."""
        from myrm_agent_harness.utils.tree_truncator import truncate_html_soup

        soup = BeautifulSoup(html, "lxml")
        if not soup.body:
            soup = BeautifulSoup(f"<body>{html}</body>", "lxml")

        ssr_variant_hashes: dict[int, Tag] = {}

        def _calculate_link_density(element: Tag) -> tuple[int, int, float]:
            text = element.get_text(strip=True)
            if not text:
                return 0, 0, 0.0
            links = element.find_all("a")
            link_text = "".join(a.get_text(strip=True) for a in links)
            return len(links), len(text), len(link_text) / len(text)

        body = soup.body
        if not body:
            return [], False

        # Over the limit only the scoring is skipped: comments, excluded tags, truncation and block extraction still run.
        within_scoring_limit = _dom_path_units(body, _MAX_SCORING_PATH_UNITS) <= _MAX_SCORING_PATH_UNITS
        scored_elements = list(body.find_all(True)) if within_scoring_limit else []

        for el in scored_elements:
            # An element decomposed together with a removed ancestor has lost its attributes.
            if not hasattr(el, "name") or el.name is None or el.name in _SKIP_TAGS:
                continue
            if not hasattr(el, "attrs"):
                continue

            should_remove = False

            try:
                class_list = el.attrs.get("class")
                if class_list and isinstance(class_list, list):
                    has_ssr = self._has_ssr_variant_class(class_list)
                    if has_ssr:
                        ch = self._compute_content_hash(el)
                        if ch is not None:
                            if ch in ssr_variant_hashes:
                                should_remove = True
                            else:
                                ssr_variant_hashes[ch] = el
                    if not should_remove and not has_ssr and self._has_hidden_class(class_list):
                        should_remove = True
            except AttributeError:
                pass

            if not should_remove:
                try:
                    if el.name in ("nav", "aside", "footer") or (
                        el.name == "header" and not self._check_in_content_area(el)
                    ):
                        should_remove = True
                except AttributeError:
                    pass

            if not should_remove:
                try:
                    if el.name not in ("section", "main", "article"):
                        area = self._check_element_area(el)
                        if area != "content":
                            link_count, text_len, link_ratio = _calculate_link_density(el)
                            if (
                                link_count >= 3
                                and text_len > 20
                                and link_ratio > 0.8
                                and not self._bfs_find_content_section(el)
                            ):
                                should_remove = True
                except AttributeError:
                    pass

            if should_remove:
                try:
                    el.decompose()
                except Exception as e:
                    logger.warning(f"Failed to remove element: {e}")

        try:
            self._remove_comments(soup)
            self._remove_unwanted_tags(soup)

            body = soup.find("body")
            if not body:
                return [], False

            if within_scoring_limit:
                self._prune_tree(body)

            if max_chars > 0:
                body, was_truncated = truncate_html_soup(body, max_chars)
            else:
                was_truncated = False

            content_blocks: list[str] = []
            for element in body.children:
                if isinstance(element, str) or not hasattr(element, "name"):
                    continue
                if len(element.get_text(strip=True)) > 0:
                    content_blocks.append(str(element))
            return content_blocks, was_truncated
        except Exception as e:
            logger.warning(f"Pruning failed: {e}")
            return [], False

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_composite_score(
        self,
        metrics: dict[str, object],
        text_len: int,
        tag_len: int,
        link_text_len: int,
    ) -> float:
        node = cast(Tag, metrics["node"])
        if self.min_word_threshold:
            text = node.get_text(strip=True)
            word_count = text.count(" ") + 1
            if word_count < self.min_word_threshold:
                return -1.0

        score = 0.0
        total_weight = 0.0

        if self.metric_config["text_density"]:
            density = text_len / tag_len if tag_len > 0 else 0
            score += self.metric_weights["text_density"] * density
            total_weight += self.metric_weights["text_density"]

        if self.metric_config["link_density"]:
            link_ratio = link_text_len / text_len if text_len > 0 else 0
            if link_ratio > 0.5:
                is_pure_list = self._is_pure_link_list(node)
                if is_pure_list:
                    if link_ratio > 0.8:
                        density = 0.3
                    elif link_ratio > 0.6:
                        density = 0.5
                    else:
                        density = 1.0
                else:
                    density = 1.0
            else:
                density = 1.0
            score += self.metric_weights["link_density"] * density
            total_weight += self.metric_weights["link_density"]

        if self.metric_config["tag_weight"]:
            tag_name = str(metrics["tag_name"])
            if tag_name == "header":
                tag_score = 0.7 if self._check_in_content_area(node) else 0.1
            else:
                tag_score = self.tag_weights.get(tag_name, 0.5)
            score += self.metric_weights["tag_weight"] * tag_score
            total_weight += self.metric_weights["tag_weight"]

        if self.metric_config["class_id_weight"]:
            class_score = self._compute_class_id_weight(node)
            score += self.metric_weights["class_id_weight"] * max(0.0, class_score)
            total_weight += self.metric_weights["class_id_weight"]

        if self.metric_config["text_length"]:
            if text_len < 10:
                length_score = 0.8
            elif text_len < 50:
                length_score = 1.0
            elif text_len < 200:
                length_score = 0.9
            else:
                length_score = min(1.0, math.log(text_len) / math.log(200))
            score += self.metric_weights["text_length"] * length_score
            total_weight += self.metric_weights["text_length"]

        final_score = score / total_weight if total_weight > 0 else 0.0

        area = self._check_element_area(node)
        if area == "navigation":
            final_score *= 0.90
        elif area == "content":
            final_score = min(1.0, final_score * 1.3)
        else:
            final_score *= 1.1

        return final_score
