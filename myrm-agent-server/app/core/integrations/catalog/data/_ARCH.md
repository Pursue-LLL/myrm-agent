# catalog/data/

## 架构概述

Integration Catalog 的静态预配置数据。按服务分类组织，每个 JSON 文件对应一个分类，CatalogRegistry 自动扫描加载。

## 文件清单

| 文件 | 分类 | 条目数 | 内容 |
|------|------|--------|------|
| `productivity.json` | productivity | 6 | Notion, Todoist, Google Calendar, Linear, Tencent Docs, WPS |
| `development.json` | development | 7 | GitHub, GitLab, Sentry, Code Review Graph, CodeGraph, Gitee, Gitee Enterprise |
| `communication.json` | communication | 5 | Gmail, Slack, 飞书, 钉钉, QQ Mail |
| `data_storage.json` | data_storage | 4 | Google Drive, PostgreSQL, File System, Supabase |
| `browser.json` | browser | 2 | Playwright, Browserbase |
| `web_search.json` | web_search | 3 | Firecrawl, Exa, Brave Search |
| `docs.json` | docs | 3 | Context7, Microsoft Learn, AWS Documentation |
| `design.json` | design | 1 | Figma |
| `api.json` | api | 2 | Postman, QiChaCha |
