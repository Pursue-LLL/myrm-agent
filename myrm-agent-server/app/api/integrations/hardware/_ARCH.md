# api/integrations/hardware/

## 架构概述

Settings Hardware Cookbook 的 HTTP 层：检测本地硬件、按 64K 上下文估算 KV Cache 显存（FP16 / Q8 / Q4）、划分 5 档 Reference Ladder 硬件段位、估算 Tokens/s，并给出 Ollama 模型适配度推荐；同时代理 Ollama 的 pull（拉取成功后自动派生 64K agentic Modelfile）与 delete，并为首页"使用本机 Ollama"一键连接挑出能对话且支持工具调用的本机模型。包导出一个 `router`，由 [../router.py](../router.py) 挂在 `/integrations/hardware` 下。上级文档：[../_ARCH.md](../_ARCH.md)。

## 路由

| 路径（相对 `/integrations/hardware`） | 方法 |
|------|------|
| `/recommendations` | GET |
| `/ollama/chat-model` | GET |
| `/ollama/pull` | POST |
| `/ollama/models` | DELETE |

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router` | ✅ |
| `cookbook.py` | 模块 | 四个端点与硬件探测结果缓存；推荐逻辑按 64K 上下文总显存给每个模型打适配分并排序。 | ✅ |
| `ollama_probe.py` | 模块 | 本机 Ollama 守护进程探测：读取已安装模型（`/api/tags`，Cookbook 的"是否已安装"与一键连接共用），并用 `/api/show` 的 capabilities 选出首个既能对话又支持工具调用的本机模型；缺 capabilities 视为未知，云端转发模型不参选。 | ✅ |
| `calculator.py` | 模块 | 显存测算、段位判定、Tokens/s 估算与适配度排序权重的纯函数。 | ✅ |
| `model_specs.py` | 模块 | 从 `myrm-agent-server/assets/cookbook_specs.json` 读取模型规格（带 1 小时缓存），`ModelSpec` 描述单条规格的字段。 | ✅ |
