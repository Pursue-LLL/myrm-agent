# clip/

Extension wiki clip UserConfig SSOT — sync clip target agent + WebUI origin between WebUI and MV3.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | Re-export clip agent config API | — |
| `agent_config.py` | 核心 | `extensionClipAgent` UserConfig get/set · `device_id="webui"` | ✅ |

## 依赖

- `app.services.config.service::ConfigService` (POS: UserConfig persistence)
- `app.schemas.config::ConfigKey` — `"extensionClipAgent"` literal SSOT

## 调用方

| Caller | Entry |
| --- | --- |
| `app/api/extension/routes/clip_agent.py` | REST `/extension/clip-agent` |
| `app.services.extension.bridge` | WS `clip_agent_update` push |

## 测试

| 文件 | 覆盖 |
| --- | --- |
| `tests/services/extension/clip/test_agent_config.py` | device_id on ConfigService.set |
| `tests/api/extension/test_clip_agent_integration.py` | GET/PUT roundtrip |
