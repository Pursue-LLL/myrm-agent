
# docker/sandbox 模块架构

Skill 执行沙箱 Docker 镜像构建项目。提供生产级容器化环境，支持 Python/Node.js 多运行时、安全隔离、健康检查和多架构构建。

详细设计和使用指南请参考 [README.md](README.md)

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `Dockerfile` | 核心 | 多阶段镜像构建定义 |
| `matplotlibrc` | 核心 | matplotlib CJK 默认字体配置（中文图表保真） |
| `pyproject.toml` | 核心 | Python 沙箱依赖声明 |
| `uv.lock` | 核心 | 依赖锁文件（确定性构建） |
| `build.sh` | 辅助 | 构建脚本（支持单/多架构） |
| `benchmark.sh` | 辅助 | 性能基准测试脚本 |
| `deep_health_check.py` | 辅助 | 深度健康检查（验证关键依赖可用性） |
| `test_image.py` | 辅助 | 镜像集成测试 |
| `CHANGELOG.md` | 文档 | 版本更新日志 |
| `README.md` | 文档 | 使用指南和设计文档 |
