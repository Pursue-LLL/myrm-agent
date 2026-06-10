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

工作流构建 macOS / Windows / Linux 安装包，合并 `latest.json`，并发布**非 draft** GitHub Release（`releases/latest` API 与官网 `bake:release` 可拾取）。签名密钥见 [SIGNING.md](SIGNING.md)。

## 本地构建

```bash
cd myrm-agent-desktop
# 详见 _ARCH.md 与 src-tauri 构建脚本
```

Sidecar 对照（Python 后端 vs Agent Runner）见 [_ARCH.md](_ARCH.md) § Sidecar 对照表。

## 许可证

MIT
