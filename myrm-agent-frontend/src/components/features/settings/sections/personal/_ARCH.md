# settings/sections/personal/ 模块架构

## 架构概述

Settings「Personal」分组：账户、偏好与个性化 Tab Section。

## 文件清单

| 文件 | 职责 |
|------|------|
| `AccountSection.tsx` | 账户信息与凭据 |
| `PreferencesSection.tsx` | 通用偏好（语言、主题等） |
| `PersonalizationSection.tsx` | 个性化与伴侣相关选项 |

## 依赖

- [sections/_ARCH.md](../_ARCH.md)
- `@/store/useConfigStore` — 设置草稿与同步
