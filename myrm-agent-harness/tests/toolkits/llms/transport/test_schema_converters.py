"""JSON-Schema rewriting for the providers whose APIs reject standard keywords with a 400."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.transport.anthropic_schema import to_output_schema
from myrm_agent_harness.toolkits.llms.transport.gemini_schema import to_gemini_schema
from myrm_agent_harness.toolkits.llms.transport.json_schema import inline_refs


class TestInlineRefs:
    def test_a_local_reference_is_replaced_by_its_definition_and_the_table_removed(self) -> None:
        schema = {
            "type": "object",
            "properties": {"home": {"$ref": "#/$defs/Address"}},
            "$defs": {"Address": {"type": "object", "properties": {"city": {"type": "string"}}}},
        }
        assert inline_refs(schema) == {
            "type": "object",
            "properties": {"home": {"type": "object", "properties": {"city": {"type": "string"}}}},
        }

    def test_sibling_keywords_of_a_reference_win_over_the_definition(self) -> None:
        schema = {
            "properties": {"n": {"$ref": "#/definitions/Num", "description": "the count"}},
            "definitions": {"Num": {"type": "integer", "description": "a number"}},
        }
        assert inline_refs(schema)["properties"] == {"n": {"type": "integer", "description": "the count"}}  # type: ignore[comparison-overlap]

    def test_a_cycle_becomes_any_value_instead_of_looping(self) -> None:
        schema = {
            "$ref": "#/$defs/Node",
            "$defs": {"Node": {"type": "object", "properties": {"next": {"$ref": "#/$defs/Node"}}}},
        }
        resolved = inline_refs(schema)
        assert resolved == {"type": "object", "properties": {"next": {}}}

    def test_an_unresolvable_or_external_reference_becomes_any_value(self) -> None:
        schema = {"properties": {"a": {"$ref": "#/$defs/Missing"}, "b": {"$ref": "https://x.test/s.json"}}}
        assert inline_refs(schema) == {"properties": {"a": {}, "b": {}}}

    def test_a_schema_without_references_is_unchanged(self) -> None:
        schema = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
        assert inline_refs(schema) == schema

    def test_a_schema_nested_beyond_the_depth_limit_is_cut_to_any_value_instead_of_recursing_forever(self) -> None:
        schema: dict[str, object] = {"type": "string"}
        for _ in range(60):
            schema = {"type": "object", "properties": {"next": schema}}

        node: object = inline_refs(schema)
        levels = 0
        while isinstance(node, dict) and "properties" in node:
            node = node["properties"].get("next", {})  # the cut can fall on the table itself
            levels += 1

        assert node == {}
        assert 10 <= levels < 60

    @pytest.mark.parametrize("malformed", [None, [], "string", 7], ids=["none", "list", "text", "number"])
    def test_a_tool_schema_that_is_not_an_object_becomes_any_value(self, malformed: object) -> None:
        assert inline_refs(malformed) == {}  # type: ignore[arg-type]


class TestGeminiSchema:
    def test_unknown_keywords_are_dropped_and_known_ones_kept(self) -> None:
        converted = to_gemini_schema(
            {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "additionalProperties": False,
                "properties": {"q": {"type": "string", "description": "query", "default": "x", "minLength": 1}},
                "required": ["q"],
            }
        )
        assert converted == {
            "type": "object",
            "properties": {"q": {"type": "string", "description": "query", "minLength": 1}},
            "required": ["q"],
        }

    def test_nullable_unions_become_the_nullable_flag(self) -> None:
        converted = to_gemini_schema(
            {
                "type": "object",
                "properties": {
                    "a": {"type": ["string", "null"]},
                    "b": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                },
            }
        )
        assert converted["properties"] == {  # type: ignore[comparison-overlap]
            "a": {"type": "string", "nullable": True},
            "b": {"type": "integer", "nullable": True},
        }

    def test_const_and_non_string_enums_become_string_enums(self) -> None:
        converted = to_gemini_schema(
            {"type": "object", "properties": {"c": {"const": "fixed"}, "n": {"type": "integer", "enum": [1, 2]}}}
        )
        assert converted["properties"] == {  # type: ignore[comparison-overlap]
            "c": {"enum": ["fixed"]},
            "n": {"type": "string", "enum": ["1", "2"]},
        }

    def test_unsupported_string_formats_are_dropped(self) -> None:
        converted = to_gemini_schema(
            {
                "type": "object",
                "properties": {
                    "u": {"type": "string", "format": "uri"},
                    "t": {"type": "string", "format": "date-time"},
                },
            }
        )
        assert converted["properties"] == {"u": {"type": "string"}, "t": {"type": "string", "format": "date-time"}}  # type: ignore[comparison-overlap]

    def test_references_are_inlined_and_array_items_converted(self) -> None:
        converted = to_gemini_schema(
            {
                "type": "object",
                "properties": {"tags": {"type": "array", "items": {"$ref": "#/$defs/Tag"}}},
                "$defs": {"Tag": {"type": "string", "additionalProperties": False}},
            }
        )
        assert converted["properties"] == {"tags": {"type": "array", "items": {"type": "string"}}}  # type: ignore[comparison-overlap]

    def test_an_object_without_properties_gets_an_empty_property_table(self) -> None:
        assert to_gemini_schema({"type": "object"}) == {"type": "object", "properties": {}}

    def test_a_typeless_root_is_an_object(self) -> None:
        assert to_gemini_schema({"properties": {"a": {"type": "string"}}}) == {
            "type": "object",
            "properties": {"a": {"type": "string"}},
        }


class TestAnthropicOutputSchema:
    def test_unenforceable_constraints_move_into_the_description(self) -> None:
        converted = to_output_schema(
            {
                "type": "object",
                "properties": {"n": {"type": "integer", "description": "count", "minimum": 1, "maximum": 5}},
            }
        )
        assert converted["properties"] == {  # type: ignore[comparison-overlap]
            "n": {"type": "integer", "description": "count Note: minimum value: 1, maximum value: 5."}
        }

    def test_every_object_forbids_additional_properties(self) -> None:
        converted = to_output_schema(
            {"type": "object", "properties": {"inner": {"type": "object", "properties": {"x": {"type": "string"}}}}}
        )
        assert converted["additionalProperties"] is False
        assert converted["properties"]["inner"]["additionalProperties"] is False  # type: ignore[index]

    def test_one_of_becomes_any_of(self) -> None:
        converted = to_output_schema({"oneOf": [{"type": "string"}, {"type": "integer"}]})
        assert converted == {"anyOf": [{"type": "string"}, {"type": "integer"}]}

    def test_references_are_inlined_first(self) -> None:
        converted = to_output_schema(
            {
                "type": "object",
                "properties": {"p": {"$ref": "#/$defs/P"}},
                "$defs": {"P": {"type": "object", "properties": {"id": {"type": "string"}}}},
            }
        )
        assert "$defs" not in converted
        assert converted["properties"]["p"]["properties"] == {"id": {"type": "string"}}  # type: ignore[index]

    def test_the_output_is_deterministic_for_identical_input(self) -> None:
        schema = {"type": "object", "properties": {"n": {"type": "integer", "maximum": 9, "minimum": 1}}}
        assert str(to_output_schema(schema)) == str(to_output_schema(dict(schema)))
