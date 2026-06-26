<p align="center">
  <a href="https://myrmagent.ai">
    <img src="https://myrmagent.ai/og-image.png" alt="MyrmAgent" width="720">
  </a>
</p>

<h1 align="center">MyrmAgent</h1>

<p align="center">
  <strong>A soulful, all-capable AI work partner</strong><br>
  Deep memory · precise answers · steady execution — powerful, with everything under your control.
</p>

<p align="center">
  <a href="README_zh.md">中文</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/Pursue-LLL/myrm-agent/stargazers"><img src="https://img.shields.io/github/stars/Pursue-LLL/myrm-agent?style=for-the-badge&logo=github&color=FFD43B" alt="GitHub Stars"></a>
  <a href="https://discord.gg/myrm"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
</p>

<p align="center">
  <a href="https://myrmagent.ai">Website</a> ·
  <a href="https://docs.myrmagent.ai">Docs</a> ·
  <a href="https://app.myrmagent.ai">Cloud</a> ·
  <a href="https://discord.gg/myrm">Discord</a> ·
  <a href="https://github.com/Pursue-LLL/myrm-agent/releases">Download</a>
</p>

---

## Core Capabilities

| Capability | Description |
|:-----------|:------------|
| **Persistent sandbox** | Agent-in-sandbox architecture — each user gets a dedicated workspace with persistent volume. Files, environment, and configs survive across sessions. |
| **Cross-session memory** | Multi-layer memory (working / episodic / semantic / shared) powered by SQLite + Qdrant. The agent truly remembers you. |
| **Agent personas** | Configure custom agents with their own system prompts, tools, skills, and memory — switch instantly in the GUI. |
| **Multi-channel access** | WhatsApp, Telegram, Discord, WeChat, DingTalk, Feishu, Slack, and 30+ more. One agent, everywhere you work. |
| **Scheduled automation** | Natural-language cron — set up recurring tasks with self-healing and heartbeat monitoring. 24/7 unattended. |
| **Multi-agent orchestration** | Parallel sub-agents with COW workspace isolation and line-level file conflict detection. |
| **Multi-modal content** | Image generation (20+ models), video creation (4 engines), voice interaction (3 modes + 5 STT providers), document writing. |
| **6-layer security** | Tool guard · file access control · PII detection · skill scanning · sandbox isolation · audit logging. |

## Deployment Modes

MyrmAgent supports three primary deployment modes — all are first-class citizens:

| Mode | How | Best for |
|:-----|:----|:---------|
| **Local WebUI** | `myrm start` → browser at `localhost:3000` | Self-host · full data sovereignty · team compliance |
| **Desktop App** | Tauri native app (macOS / Windows / Linux) | Daily desktop workflow · auto-launch · close-to-tray |
| **Cloud Hosted** | Control plane provisions isolated sandboxes per user | Zero-ops · 24/7 uptime · WU-based billing |

## Quick Start

### One-line install (any directory)

```bash
curl -fsSL https://myrmagent.ai/install.sh | bash
```

### From source

```bash
git clone https://github.com/Pursue-LLL/myrm-agent.git
cd myrm-agent
bash scripts/install.sh
myrm start
```

Open **http://localhost:3000** and configure your LLM provider in the GUI.

### Desktop App

Download the latest release for your platform from [Releases](https://github.com/Pursue-LLL/myrm-agent/releases).

## Integrations

**100+ LLM models** — OpenAI · Anthropic · Google Gemini · DeepSeek · Qwen · Local models via Ollama

**Built-in tools** — MCP Protocol · Browser · File System · Terminal · Code Execution · @codebase Overview · Web Search · Database · Cron Jobs

## Documentation

| Resource | Link |
|:---------|:-----|
| Architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Module guide | [_ARCH.md](_ARCH.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Security | [SECURITY.md](SECURITY.md) |

## License

[MIT](LICENSE) — free to use, modify, and distribute.
