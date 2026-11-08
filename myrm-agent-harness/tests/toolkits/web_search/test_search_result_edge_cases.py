"""SearchResult construction from provider payloads (core/common.py).

[POS]
Unit tests for SearchResult.from_dict: which payload field fills which attribute, and how missing or malformed
fields are handled.
"""

from myrm_agent_harness.toolkits.web_search.core.common import SearchResult


class TestSearchResultEdgeCases:
    """测试 SearchResult 边缘情况"""

    def test_from_dict_with_content_field(self) -> None:
        """测试使用 content 字段"""
        data = {
            "title": "Test",
            "link": "https://example.com",
            "content": "Content from content field",
        }
        result = SearchResult.from_dict(data)
        assert result.snippet == "Content from content field"

    def test_from_dict_with_text_field(self) -> None:
        """测试使用 text 字段"""
        data = {
            "title": "Test",
            "url": "https://example.com",
            "text": "Content from text field",
        }
        result = SearchResult.from_dict(data)
        assert result.link == "https://example.com"
        assert result.snippet == "Content from text field"

    def test_from_dict_no_title(self) -> None:
        """测试无标题情况"""
        data = {
            "link": "https://example.com",
            "snippet": "Test snippet",
        }
        result = SearchResult.from_dict(data)
        assert result.title == "Untitled"

    def test_from_dict_with_date(self) -> None:
        """测试带日期的结果"""
        data = {
            "title": "News",
            "link": "https://news.example.com",
            "snippet": "Breaking news",
            "date": "2024-03-19",
        }
        result = SearchResult.from_dict(data)
        assert result.date == "2024-03-19"

    def test_from_dict_with_engines(self) -> None:
        """测试带引擎信息的结果"""
        data = {
            "title": "Multi-engine result",
            "link": "https://example.com",
            "snippet": "Found by multiple engines",
            "engines": ["google", "bing"],
        }
        result = SearchResult.from_dict(data)
        assert result.engines == ["google", "bing"]

    def test_from_dict_with_null_text_fields(self) -> None:
        """测试文本字段均为 None 时按空文本处理"""
        data = {"title": "T", "link": "https://example.com", "snippet": None, "content": None, "text": None}
        result = SearchResult.from_dict(data)
        assert result.snippet == ""

    def test_from_dict_parses_citations_and_skips_entries_without_url(self) -> None:
        """测试引用解析：缺少 url 或非字典的条目被跳过"""
        data = {
            "title": "T",
            "link": "https://example.com",
            "snippet": "S",
            "citations": [
                {"url": "https://example.com/ref", "title": "Ref", "start_index": 3, "end_index": 9},
                {"title": "no url"},
                "not a dict",
            ],
        }
        result = SearchResult.from_dict(data)
        assert [(c.url, c.title, c.start_index, c.end_index) for c in result.citations] == [
            ("https://example.com/ref", "Ref", 3, 9)
        ]

    def test_from_dict_leaves_the_serving_provider_to_the_searcher(self) -> None:
        """测试 provider 由搜索器在返回结果时标注，原始响应不携带"""
        result = SearchResult.from_dict({"title": "T", "link": "https://example.com", "snippet": "S"})
        assert result.provider is None
