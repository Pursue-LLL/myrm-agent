# webui 服务模块


---

## 架构概述

WebUI 辅助服务包，只保留二维码、URL 组装和本机地址解析等纯展示能力。身份认证、临时 Token、用户管理已移出该包。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `qrcode.py` | ✅ 核心 | 二维码生成与 WebUI 访问 URL 组装：ASCII 终端展示、PNG 图片输出、URL 拼装辅助。 |
| `__init__.py` | ✅ 包标记 | 仅声明包，不再导出旧认证对象。 |

---

## 依赖关系

### 内部依赖
- `app.config.settings`：WebUI 端口与二维码尺寸配置

### 外部依赖
- `myrm_agent_harness.utils.get_local_ip`：本机 IP 解析
