<p align="center">
  <a href="https://myrmagent.ai">
    <img src="https://myrmagent.ai/og-image.png" alt="MyrmAgent" width="720">
  </a>
</p>

<h1 align="center">MyrmAgent</h1>

<p align="center">
  <strong>有灵魂的 AI 全能工作伙伴</strong><br>
  记得深、答的准、跑的稳 —— 强大又一切都在掌控之中。
</p>

<p align="center">
  <a href="README.md">English</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/Pursue-LLL/myrm-agent/stargazers"><img src="https://img.shields.io/github/stars/Pursue-LLL/myrm-agent?style=for-the-badge&logo=github&color=FFD43B" alt="GitHub Stars"></a>
  <a href="https://discord.gg/myrm"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
</p>

<p align="center">
  <a href="https://myrmagent.ai">官网</a> ·
  <a href="https://docs.myrmagent.ai">文档</a> ·
  <a href="https://app.myrmagent.ai">云端</a> ·
  <a href="https://discord.gg/myrm">Discord</a> ·
  <a href="https://github.com/Pursue-LLL/myrm-agent/releases">下载</a>
</p>

---

## 核心能力

| 能力 | 说明 |
|:-----|:-----|
| **持久沙箱** | Agent-in-sandbox 架构 —— 每个用户拥有专属工作空间和持久卷。文件、环境、配置跨会话保留。 |
| **跨会话记忆** | 多层记忆（工作 / 情景 / 语义 / 共享），基于 SQLite + Qdrant，真正记住你。 |
| **智能体配置** | 自定义智能体的提示词、工具、技能和记忆 —— 在 GUI 中一键切换。 |
| **多渠道接入** | WhatsApp、Telegram、Discord、微信、钉钉、飞书、Slack 等 30+ 渠道。一个 Agent，随处可用。 |
| **定时自动化** | 自然语言定时任务，自愈 + 心跳监控，7x24 无人值守。 |
| **多 Agent 协作** | 并行子 Agent，COW 工作空间隔离 + 行级文件冲突检测。 |
| **多模态内容** | 图片生成（20+ 模型）、视频创作（4 引擎）、语音交互（3 模式 + 5 STT 提供商）、文档撰写。 |
| **6 层安全防御** | 工具守卫 · 文件访问控制 · PII 检测 · 技能扫描 · 沙箱隔离 · 审计日志。 |

## 部署模式

MyrmAgent 支持三种部署模式，均为产品主力：

| 模式 | 方式 | 适用场景 |
|:-----|:-----|:---------|
| **本地 WebUI** | `myrm start` → 浏览器访问 `localhost:3000` | 自托管 · 数据主权 · 合规要求 |
| **桌面客户端** | Tauri 原生应用（macOS / Windows / Linux） | 日常桌面工作流 · 开机自启 · 托盘运行 |
| **云托管** | 控制平面为每个用户分配独立沙箱 | 零运维 · 24/7 在线 · WU 按量计费 |

## 快速开始

### 一键安装（任意目录）

```bash
curl -fsSL https://myrmagent.ai/install.sh | bash
```

### 从源码安装

```bash
git clone https://github.com/Pursue-LLL/myrm-agent.git
cd myrm-agent
bash scripts/install.sh
myrm start
```

打开 **http://localhost:3000**，在 GUI 中配置你的 LLM 提供商。

### 桌面客户端

从 [Releases](https://github.com/Pursue-LLL/myrm-agent/releases) 下载适合你平台的最新版本。

## 集成

**100+ LLM 模型** — OpenAI · Anthropic · Google Gemini · DeepSeek · 通义千问 · 本地模型（Ollama）

**内置工具** — MCP 协议 · 浏览器 · 文件系统 · 终端 · 代码执行 · @codebase 搜索 · 网络搜索 · 数据库 · 定时任务

## 文档

| 资源 | 链接 |
|:-----|:-----|
| 架构说明 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 模块指南 | [_ARCH.md](_ARCH.md) |
| 贡献指南 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| 安全披露 | [SECURITY.md](SECURITY.md) |

## 许可证

[MIT](LICENSE) — 自由使用、修改和分发。
