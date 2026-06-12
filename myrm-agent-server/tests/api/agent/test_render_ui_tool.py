"""render_ui 工具测试

验证 render_ui 工具正确解析组件 JSON 并注册 UIArtifact，
重点覆盖 tabs 组件的端到端解析流程。
"""

from myrm_agent_harness.agent.artifacts.context import ArtifactContextManager
from myrm_agent_harness.agent.artifacts.ui_registry import get_ui_registry
from myrm_agent_harness.agent.meta_tools.interaction.render_ui_tool import render_ui


class TestRenderUITool:
    """render_ui 工具解析测试。"""

    def test_render_tabs_ui(self):
        """验证 tabs 组件从 JSON 到 UIArtifact 的完整解析链路。"""
        with ArtifactContextManager():
            result = render_ui(
                title="手机对比",
                components=[
                    {
                        "id": "tabs1",
                        "type": "tabs",
                        "props": {"tabs": [{"label": "iPhone 16"}, {"label": "Galaxy S25"}]},
                        "children": ["card_iphone", "card_galaxy"],
                    },
                    {
                        "id": "card_iphone",
                        "type": "card",
                        "props": {"title": "iPhone 16"},
                        "children": ["text_iphone"],
                    },
                    {
                        "id": "card_galaxy",
                        "type": "card",
                        "props": {"title": "Galaxy S25"},
                        "children": ["text_galaxy"],
                    },
                    {
                        "id": "text_iphone",
                        "type": "text",
                        "props": {"text": "A18 Pro 芯片"},
                    },
                    {
                        "id": "text_galaxy",
                        "type": "text",
                        "props": {"text": "Snapdragon 8 Gen 4"},
                    },
                ],
                root_ids=["tabs1"],
                data={},
            )

            assert "手机对比" in result

            registry = get_ui_registry()
            assert registry is not None
            events = registry.pop_pending_events()
            assert len(events) == 1

            artifact = events[0]
            d = artifact.to_dict()
            assert d["title"] == "手机对比"
            assert len(d["components"]) == 5
            assert d["root_ids"] == ["tabs1"]

            tabs_comp = d["components"][0]
            assert tabs_comp["type"] == "tabs"
            assert tabs_comp["props"]["tabs"] == [{"label": "iPhone 16"}, {"label": "Galaxy S25"}]
            assert tabs_comp["children"] == ["card_iphone", "card_galaxy"]

    def test_render_basic_form_ui(self):
        """验证基础表单 UI 的解析。"""
        with ArtifactContextManager():
            result = render_ui(
                title="用户信息",
                components=[
                    {
                        "id": "name",
                        "type": "text_field",
                        "props": {"label": "姓名", "placeholder": "请输入"},
                        "bindings": {"value": "$.form.name"},
                    },
                ],
                root_ids=["name"],
                data={"form": {"name": ""}},
            )

            assert "用户信息" in result
            registry = get_ui_registry()
            assert registry is not None
            events = registry.pop_pending_events()
            assert len(events) == 1
            assert events[0].data == {"form": {"name": ""}}

    def test_render_unknown_component_type_skipped(self):
        """未知组件类型应被跳过，不导致崩溃。"""
        with ArtifactContextManager():
            result = render_ui(
                title="Test",
                components=[
                    {"id": "valid", "type": "text", "props": {"text": "hello"}},
                    {"id": "invalid", "type": "nonexistent_type", "props": {}},
                ],
                root_ids=["valid"],
            )

            assert "Test" in result
            registry = get_ui_registry()
            assert registry is not None
            events = registry.pop_pending_events()
            assert len(events) == 1
            assert len(events[0].components) == 1

    def test_render_ui_with_actions(self):
        """验证带动作的 UI 解析。"""
        with ArtifactContextManager():
            result = render_ui(
                title="确认",
                components=[
                    {
                        "id": "btn",
                        "type": "button",
                        "props": {"label": "提交"},
                        "events": {"onClick": "submit"},
                    },
                ],
                root_ids=["btn"],
                actions=[{"id": "submit", "type": "submit", "label": "确认提交"}],
            )

            assert "确认" in result
            registry = get_ui_registry()
            assert registry is not None
            events = registry.pop_pending_events()
            assert len(events[0].actions) == 1
            assert events[0].actions[0].type == "submit"

    def test_render_ui_outside_context(self):
        """在 ArtifactContext 之外调用不崩溃，返回警告。"""
        result = render_ui(
            title="No Context",
            components=[{"id": "t", "type": "text", "props": {"text": "x"}}],
            root_ids=["t"],
        )
        assert "No Context" in result

    def test_render_tabs_with_default_index(self):
        """验证 tabs 的 defaultIndex prop 正确传递。"""
        with ArtifactContextManager():
            render_ui(
                title="带默认索引的 Tabs",
                components=[
                    {
                        "id": "tabs",
                        "type": "tabs",
                        "props": {
                            "tabs": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
                            "defaultIndex": 2,
                        },
                        "children": ["a", "b", "c"],
                    },
                    {"id": "a", "type": "text", "props": {"text": "Panel A"}},
                    {"id": "b", "type": "text", "props": {"text": "Panel B"}},
                    {"id": "c", "type": "text", "props": {"text": "Panel C"}},
                ],
                root_ids=["tabs"],
            )

            registry = get_ui_registry()
            assert registry is not None
            events = registry.pop_pending_events()
            tabs_comp = events[0].components[0]
            assert tabs_comp.props["defaultIndex"] == 2
            assert len(tabs_comp.props["tabs"]) == 3

    def test_render_empty_components(self):
        """空组件列表不崩溃。"""
        with ArtifactContextManager():
            result = render_ui(title="Empty", components=[], root_ids=[])
            assert "Empty" in result
            registry = get_ui_registry()
            assert registry is not None
            events = registry.pop_pending_events()
            assert len(events) == 1
            assert len(events[0].components) == 0

    def test_render_nested_tabs(self):
        """嵌套 tabs 的解析（tabs 内包含 tabs）。"""
        with ArtifactContextManager():
            render_ui(
                title="嵌套 Tabs",
                components=[
                    {
                        "id": "outer",
                        "type": "tabs",
                        "props": {"tabs": [{"label": "Outer A"}, {"label": "Outer B"}]},
                        "children": ["inner_tabs", "text_b"],
                    },
                    {
                        "id": "inner_tabs",
                        "type": "tabs",
                        "props": {"tabs": [{"label": "Inner 1"}, {"label": "Inner 2"}]},
                        "children": ["t1", "t2"],
                    },
                    {"id": "t1", "type": "text", "props": {"text": "Nested 1"}},
                    {"id": "t2", "type": "text", "props": {"text": "Nested 2"}},
                    {"id": "text_b", "type": "text", "props": {"text": "Outer B content"}},
                ],
                root_ids=["outer"],
            )
            registry = get_ui_registry()
            assert registry is not None
            events = registry.pop_pending_events()
            assert len(events[0].components) == 5
            inner = [c for c in events[0].components if c.id == "inner_tabs"][0]
            assert inner.type.value == "tabs"
            assert inner.children == ["t1", "t2"]

    def test_render_component_missing_id(self):
        """组件缺少 id 字段时使用空字符串，不崩溃。"""
        with ArtifactContextManager():
            result = render_ui(
                title="No ID",
                components=[{"type": "text", "props": {"text": "hello"}}],
                root_ids=[""],
            )
            assert "No ID" in result
            registry = get_ui_registry()
            assert registry is not None
            events = registry.pop_pending_events()
            assert len(events[0].components) == 1
