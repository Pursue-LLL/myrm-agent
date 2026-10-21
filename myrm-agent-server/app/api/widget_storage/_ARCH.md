# widget_storage 模块架构

## 职责

Widget KV Storage REST API。为沙箱内 widget iframe 提供持久化键值存储，通过宿主 postMessage bridge 访问。

## 文件清单

| 文件 | 职责 |
|------|------|
| `router.py` | CRUD 端点：GET/PUT/DELETE by namespace + key |
| `__init__.py` | 模块入口 |

## 依赖

- `app.database.models.widget_kv::WidgetKVEntry` — SQLite ORM 模型
- `app.database.connection::get_db` — 异步 session provider
