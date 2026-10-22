# services/artifacts/embed_bridge 架构说明

---

## 模块定位

`EmbedBridgeService` 是面向外部网站与宿主系统的可嵌入智能体小部件（Embeddable Agent Widget）与双向上下文通信桥（Host Context Bridge）的业务服务层（Item 41 P1）。
负责接入底层 Harness 框架的 `HostContextBridgeEngine`，承载跨域 Origin 访问白名单校验、宿主网页上下文（URL、选中文本、激活表单键值对）的 `@host_context` 结构化注入与管理、以及单行 HTML/JS 嵌入代码片段的生成。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `service.py` | 核心 | 单例 `EmbedBridgeService`，提供安全策略配置、Origin 鉴权、宿主快照提交与代码片段生成 |
| `__init__.py` | 门面 | 聚合导出 `EmbedBridgeService` |
| `_ARCH.md` | 文档 | 模块定位与架构规范索引 |

---

## 依赖关系

- `myrm_agent_harness.toolkits.artifacts.embed_bridge`
