# MyrmAgent Desktop

> MIT · Tauri 桌面客户端，内嵌 Python 后端 Sidecar + Next 静态导出。

模块架构见 **[_ARCH.md](_ARCH.md)** · Rust 模块 **[src-tauri/src/_ARCH.md](src-tauri/src/_ARCH.md)**。

## 安装

从 [GitHub Releases](https://github.com/Pursue-LLL/myrm-agent/releases/latest) 或 [myrmagent.ai/download](https://myrmagent.ai/download) 下载安装包。

## 发布（CI）

推送语义化 tag 触发 `.github/workflows/desktop-release.yml`：

```bash
git tag v0.1.0
git push origin v0.1.0
```

工作流构建 macOS（Apple Silicon 优先发布）/ Windows / Linux 安装包；`finalize-release` 生成 `latest.json` 与各资产 `.sha256`，并发布**非 draft** GitHub Release（`releases/latest` API 与官网 `bake:release` 可拾取）。版本号从 git tag 注入 `tauri.conf.json`。签名密钥见 [DESKTOP_RELEASE_SYSTEM.md](DESKTOP_RELEASE_SYSTEM.md)。

## 本地构建

路径相对于 **myrm-agent 仓库根**（`open-perplexity` 联调根下为 `myrm-agent/myrm-agent-desktop`）：

```bash
cd myrm-agent-desktop

# 1. Sidecar 二进制（Python 后端 + Agent Runner）
python sidecar/build.py

# 2. Next standalone（Tauri bundle 资源）
bash scripts/build-frontend.sh

# 3. Tauri 开发（自动拉起 frontend dev server）
cd src-tauri && cargo tauri dev
```

Sidecar 对照（Python 后端 vs Agent Runner）见 [_ARCH.md](_ARCH.md) § Sidecar 对照表。

## 许可证

MIT
