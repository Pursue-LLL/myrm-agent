# Myrm Skill Sandbox

统一的生产级 Docker 沙箱镜像：开发、测试、生产使用同一镜像。

## 核心特性

### 环境统一
- ✅ **单一镜像策略**：开发、测试、生产环境完全一致
- ✅ **依赖锁定**：使用 uv + uv.lock 确保版本一致性
- ✅ **预装依赖**：70+ Python 包 + 5 个 npm 全局包，开箱即用

### 多运行时支持
- Python 3.14（主运行时）
- Node.js 20 + Bun（JavaScript/TypeScript）

### 预装能力
- **数据科学**: pandas, numpy, scipy, scikit-learn, statsmodels
- **可视化**: matplotlib, seaborn
- **文件处理**: 
  - Excel: openpyxl, xlsxwriter, xlrd
  - Word: python-docx
  - PowerPoint: python-pptx, pptxgenjs (Node.js)
  - PDF: pypdf, pdfplumber, pypdfium2, pdf2image, pdfkit, reportlab, img2pdf
  - 图像: pillow, sharp (Node.js)
- **数学计算**: sympy, mpmath
- **搜索工具**: ripgrep, fd-find
- **版本控制**: git
- **字体**: Noto CJK（中日韩）, Noto Color Emoji, Liberation（Latin）
- **中文图表**: matplotlib 默认字体指向 Noto CJK，中文标签/标题不豆腐块（字体缓存经 `MPLCONFIGDIR` 落到可写 tmpfs，运行期首图构建后复用）
- **数据格式**: pyarrow, orjson, pyyaml

### 安全隔离
- 非 root 用户运行（`sandbox`）
- ReadonlyRootfs（只读根文件系统）
- CapDrop ALL + CapAdd NET_BIND_SERVICE
- Docker 默认 seccomp profile（阻止 44 个危险系统调用）
- no-new-privileges（防止权限提升）

### 健康检查
- **分层策略**：轻量检查（60s）+ 深度检查（5 分钟）
- **轻量检查**：验证 Python 运行时和 uv 工具（<1% CPU）
- **深度检查**：验证关键依赖可用性（pandas、numpy、pdfplumber 等）
- **工具**：`deep-health-check` 脚本，可手动调用或自动调度

### 可观测性
- **Prometheus Metrics**：容器创建时间、健康检查耗时、失败原因分类
- **数据驱动**：P50/P95/P99 延迟分布，支持性能分析和优化

### 多架构支持
- **支持平台**：linux/amd64 + linux/arm64
- **原生运行**：Apple Silicon Mac、AWS Graviton 无需模拟
- **构建策略**：PR 单架构（快速），main 双架构（完整）

---

## 快速开始

### 构建镜像

```bash
cd myrm-agent-server/docker/sandbox

# 单架构构建（默认 amd64）
./build.sh latest

# 多架构构建（amd64 + arm64）
./build.sh latest linux/amd64,linux/arm64
```

构建脚本会：
1. 使用 uv 安装 Python 依赖
2. 使用 BuildKit 缓存加速
3. 测量构建时间并记录到 `.build-metrics.csv`
4. 支持单架构或多架构构建（基于第二个参数）

### 测试镜像

```bash
# Python 包验证
docker run --rm myrm/skill-sandbox:latest \
  python -c "import pandas, numpy; print('✅ OK')"

# Node.js 包验证
docker run --rm myrm/skill-sandbox:latest \
  node -e "require('pptxgenjs'); console.log('✅ OK')"

# 深度健康检查（验证所有关键依赖）
docker run --rm myrm/skill-sandbox:latest deep-health-check
```

### 性能测量

使用自动化脚本：

```bash
./benchmark.sh
```

输出示例：
```
镜像大小: 1.2GB
层数: 12
启动时间: 0.8s
内存占用: 45MB
```

---

## 架构设计

### 多阶段构建

```dockerfile
# Stage 1: Builder
FROM python:3.14-slim AS builder
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --prefix /install

# Stage 2: Runtime
FROM python:3.14-slim AS runtime
COPY --from=builder /install /usr/local
```

**优势**：
- Runtime 镜像不含构建工具（gcc、make）
- 最终镜像更小、更安全
- 符合容器安全最佳实践

### uv 包管理

**为什么用 uv 而非 pip + requirements.txt**：

| 特性 | uv | pip + requirements.txt |
|------|-----|----------------------|
| **速度** | 显著更快（Rust 实现） | 基准 |
| **lockfile** | ✅ uv.lock（确定性构建） | ❌ 需手动 pip freeze |
| **跨平台** | ✅ 完美支持 | ⚠️ 可能不一致 |
| **缓存** | ✅ 自动缓存 | ⚠️ 需手动配置 |
| **解析器** | ✅ Rust 实现 | ⚠️ Python 实现 |

**性能参考**：根据 [uv 官方文档](https://github.com/astral-sh/uv)，uv 在依赖解析和安装速度上比 pip 快 10-100x（实际效果受网络和依赖数量影响）。

**构建流程**：
1. `pyproject.toml` 定义依赖
2. `uv sync` 生成 `uv.lock`（确定性）
3. Dockerfile 使用 `uv sync --frozen` 安装（确保版本一致）

### 依赖分层策略

按变化频率分层，优化 Docker 层缓存：

1. **Layer 1: 用户创建**（极少变化）
2. **Layer 2: 系统依赖**（apt-get install，很少变化）
3. **Layer 3: Node.js + Bun**（偶尔变化）
4. **Layer 4: npm 全局包**（偶尔变化）
5. **Layer 5: Python 依赖**（频繁变化，使用 BuildKit cache mount）
6. **Layer 6: uv 工具**（很少变化）
7. **Layer 7: 工作目录**（极少变化）

**效果**：依赖未变化时，Layer 1-4 缓存命中，显著减少重复构建时间（实际效果需实测验证）。

### BuildKit 缓存挂载

```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --prefix /install

RUN --mount=type=cache,target=/root/.npm \
    npm install -g pptxgenjs sharp react react-dom react-icons
```

**优势**：
- 依赖缓存跨构建复用
- 加速重复构建（预期 2-5x，需实测验证）
- 缓存不计入镜像大小

---

## 设计决策

### 为什么统一镜像？

**优点**：
- 环境一致性 100%（消除"在我机器上能跑"问题）
- 测试准确性提升（测试环境 = 生产环境）
- 维护简单（只需维护一个 Dockerfile）
- 用户体验佳（预装依赖，开箱即用）

**缺点**：
- 镜像较大（实际大小需构建后测量）
- 存储占用（预装依赖需要磁盘空间）

**权衡**：选择"环境一致性 > 镜像大小"。磁盘和网络成本可接受（现代硬件），开发者时间 > 存储成本。

### 为什么预装依赖？

**优点**：
- 性能稳定（无需等待依赖安装）
- 离线可用（无需网络连接）
- 版本锁定（避免依赖冲突）

**缺点**：
- 空间浪费（某些技能用不上所有包）
- 灵活性低（无法针对不同技能优化）

**权衡**：选择"性能稳定 > 镜像大小"。大多数技能需要常见依赖（数据科学、文件处理），用户体验优先（无等待）。

### 为什么用 python:3.14-slim？

**备选方案**：
- `python:3.14-alpine` - 更小但需要编译多数包
- `python:3.14` - 更大且包含不必要的包

**权衡**：
- slim: 兼容性好，构建快，大小适中
- alpine: 镜像更小，但构建慢且可能有兼容性问题
- full: 包含不必要的包

**选择**：slim，兼容性和构建速度优先。

### ADR-001: seccomp Profile 选择

**背景**：容器安全需要限制系统调用，防止容器逃逸。

**决策**：使用 Docker 默认 seccomp profile（不使用 `unconfined`）。

**理由**：
- 默认 profile 阻止 44 个危险系统调用（`ptrace`、`keyctl`、`bpf` 等）
- 对正常应用无影响（Python、Node.js、Java 运行时不需要这些调用）
- 符合 CIS Docker Benchmark 安全基线

**备选方案**：
- `unconfined`：允许所有系统调用，极不安全
- 自定义 profile：维护成本高，除非有特殊需求

**影响**：堵住容器逃逸的关键漏洞，适合多租户 Sandbox 环境。

### ADR-002: 健康检查策略

**背景**：需要检测容器是否可用，但不能消耗过多资源。

**决策**：分层健康检查策略
- 轻量检查（HEALTHCHECK）：每 60s，只验证 Python 运行时
- 深度检查（deep-health-check）：每 5 分钟，验证关键依赖（pandas、numpy、pdfplumber 等）

**理由**：
- 轻量检查：低开销（<1% CPU），快速响应
- 深度检查：高可靠性，真实检测依赖损坏

**备选方案**：
- 只用轻量检查：快但不可靠（依赖损坏时无法检测）
- 只用深度检查：可靠但开销高（估算 6-10% CPU）

**影响**：平衡性能和可靠性，避免误报（容器看起来健康但实际不可用）。

### ADR-003: 多架构支持策略

**背景**：开发者使用不同架构（x86_64、Apple Silicon），生产环境也在迁移到 ARM。

**决策**：支持 amd64 + arm64 双架构
- PR/develop 分支：只构建 amd64（快速反馈）
- main 分支：构建双架构（完整发布）

**理由**：
- Apple Silicon Mac：原生运行性能提升（Apple 官方数据：对比 Rosetta 模拟最高 10x，典型场景 2-3x）
- AWS Graviton：成本降低（AWS 官方数据：对比 x86 最高 20%）
- CI 效率：PR 阶段避免双倍构建时间

**备选方案**：
- 只支持 amd64：开发体验差，Apple Silicon 用户痛苦
- 所有分支都构建双架构：CI 时间翻倍，反馈慢

**影响**：开发体验质的飞跃，同时保持 CI 效率。

### ADR-004: uv vs pip

**背景**：Python 包管理需要快速、确定性、跨平台一致。

**决策**：使用 uv + pyproject.toml + uv.lock

**理由**：
- 速度：uv 官方数据显示比 pip 快 10-100x（实际受网络影响）
- 确定性：uv.lock 锁定所有传递依赖，确保重复构建一致
- 跨平台：统一的 lockfile 格式

**风险缓解**：
- CI 验证 lockfile 同步（`uv lock --check`）
- 推荐在 Linux 环境生成 lockfile（与构建环境一致）

**备选方案**：
- pip + requirements.txt：成熟但慢，无原生 lockfile 支持
- Poetry：功能全但依赖解析慢于 uv

**影响**：构建速度提升（uv 官方数据：比 pip 快 10-100x），依赖版本一致性保证。

### ADR-005: matplotlib CJK 字体保真

**背景**：沙箱已安装 Noto CJK 系统字体（浏览器截图/PDF 导出中文正常），但 matplotlib 有独立的硬默认 `font.sans-serif=DejaVu Sans`（无 CJK），导致 agent 生成的中文数据图表标签渲染为豆腐块 □□□ 并刷出 glyph 缺失告警。

**决策**：镜像内预置 `matplotlibrc`（默认 sans-serif 指向 Noto CJK + `axes.unicode_minus=False`），以 `MATPLOTLIBRC=/opt/mpl-config/matplotlibrc` 加载配置；以 `MPLCONFIGDIR=/tmp/matplotlib` 把字体缓存落到可写 tmpfs；构建时 fail-fast 验证默认字体解析到 Noto CJK。

**理由**：
- 与字体安装同层、单一来源，配置随字体走
- 全局生效（不止 code_execution，任何 matplotlib 调用都受益），运行时零开销
- **配置加载**用 `MATPLOTLIBRC`（直指文件）而非把 `MPLCONFIGDIR` 当配置目录：`matplotlib_fname()` 对 `MATPLOTLIBRC` 仅做 `os.path.exists` 检查；而配置目录经 `get_configdir()` 在不可写时回退临时目录、静默丢弃配置——故只读 rootfs 下必须用 `MATPLOTLIBRC` 才能可靠加载
- **缓存目录**用 `MPLCONFIGDIR=/tmp/matplotlib`：字体缓存（`fontlist.json`）必须可写，只读 rootfs 下 `~/.cache` 为 root 属主/只读会导致每次执行重建缓存（冷建需扫描全部系统字体、秒级开销）；指向可写 tmpfs `/tmp` 后容器内多次绘图共享复用。`MATPLOTLIBRC` 直指文件的优先级高于 `get_configdir()`，故二者并存不冲突：配置仍从 `/opt` 加载，仅缓存改落 `/tmp`
- 字体缺失时安全回退 DejaVu，非 CJK 环境不受影响

**备选方案**：
- `MPLCONFIGDIR=/opt/mpl-config`（误用作配置目录）：只读 rootfs 下 `get_configdir()` 回退临时目录 → matplotlibrc 不被加载、运行时中文又成豆腐块（构建时 /opt 可写会误通过，运行时静默失效）。故配置走 `MATPLOTLIBRC`，`MPLCONFIGDIR` 仅用于可写缓存目录
- 运行时在执行钩子里设 rcParams：只覆盖单一路径、每次执行有开销、且框架层无法保证环境字体
- 不配置：中文图表不可用（豆腐块）

**影响**：中文数据可视化端到端可用，覆盖本地/桌面/SaaS 三种部署（同一沙箱镜像）。

---

## 维护指南

### 更新依赖

1. 修改 `pyproject.toml`：

```toml
dependencies = [
    "pandas==2.3.0",  # 更新版本
    "new-package==1.0.0",  # 添加新包
]
```

2. 重新生成锁文件：

```bash
# 在宿主机运行（确保有 uv）
cd myrm-agent-server/docker/sandbox
uv lock

# ⚠️ 跨平台验证：lockfile 应在 Linux 环境中生成或验证
# CI 会自动检查 lockfile 与 pyproject.toml 是否同步
```

**注意**：uv 会根据平台选择不同的 wheel。为确保 Linux Docker 环境中构建成功，推荐在 Linux 环境（或 CI）中生成 lockfile。CI 会自动验证一致性（`uv lock --check`）。

3. 重新构建镜像：

```bash
./build.sh latest
```

4. 验证：

```bash
docker run --rm myrm/skill-sandbox:latest \
  python -c "import new_package; print('✅ OK')"
```

### 版本管理

```bash
# 构建带版本号的镜像
./build.sh v1.1.0

# 推送到 Docker Hub（如果需要）
docker push myrm/skill-sandbox:v1.1.0
docker push myrm/skill-sandbox:latest
```

### 回滚

```bash
# 切换到特定版本
docker pull myrm/skill-sandbox:v1.0.0
docker tag myrm/skill-sandbox:v1.0.0 myrm/skill-sandbox:latest
```

---

## 性能基准

### 测量方法

| 指标 | 命令 | 说明 |
|------|------|------|
| 镜像大小 | `docker images myrm/skill-sandbox:latest` | 受预装包数量影响 |
| 构建时间 | `time docker build -f Dockerfile .` | 完全无缓存 |
| 启动时间 | `time docker run --rm <image> python -c "print('ok')"` | 容器创建到就绪 |
| 内存占用 | `docker stats --no-stream <container_id>` | 空载内存 |

**注**：实际性能需在目标环境中实测，受硬件、网络、Docker 版本影响。

### 业界参考

| 项目 | 镜像大小 | 说明 |
|------|---------|------|
| Jupyter Docker Stacks | 1.5-2.5GB | 数据科学环境 |
| VS Code Server | 1.0-1.5GB | 开发环境 |
| Anaconda | 3-5GB | 完整数据科学栈 |

**定位**：我们的镜像在同类产品的合理范围内（实际大小需构建后测量）。

### 可观测性指标

**关键 Prometheus Metrics**：

| 指标 | 类型 | 说明 |
|------|------|------|
| `sandbox_health_check_seconds{check_type}` | Histogram | 健康检查耗时（轻量/深度） |
| `sandbox_health_checks_total{result}` | Counter | 健康检查结果计数 |
| `sandbox_deep_health_checks_total{result}` | Counter | 深度检查结果计数 |
| `sandbox_container_creation_seconds` | Histogram | 容器创建耗时 |

**查询示例**（Prometheus PromQL）：
```promql
# 健康检查 P95 延迟
histogram_quantile(0.95, rate(sandbox_health_check_seconds_bucket[5m]))

# 深度检查成功率
sum(rate(sandbox_deep_health_checks_total{result="success"}[5m])) 
/ sum(rate(sandbox_deep_health_checks_total[5m]))

# 容器创建时间趋势
rate(sandbox_container_creation_seconds_sum[5m]) 
/ rate(sandbox_container_creation_seconds_count[5m])
```

---

## 故障排查

### 常见问题

#### 构建失败：无法安装包

```bash
# 错误：uv sync failed
# 原因：uv.lock 过期

# 解决：重新生成锁文件
uv lock --upgrade
```

#### 容器启动失败：健康检查不通过

```bash
# 错误：Unhealthy
# 原因：Python 运行时或 uv 工具不可用

# 调试：手动运行健康检查
docker run --rm myrm/skill-sandbox:latest \
  sh -c 'python -c "import sys; sys.exit(0)" && uv --version'
```

#### 容器无法写入文件

```bash
# 错误：Read-only file system
# 原因：使用了 ReadonlyRootfs

# 解决：写入到 /tmp 或 /persistent 卷
docker run --rm -v $(pwd)/data:/persistent myrm/skill-sandbox:latest \
  python -c "open('/persistent/test.txt', 'w').write('ok')"
```

### 调试技巧

```bash
# 进入容器 shell
docker run --rm -it myrm/skill-sandbox:latest bash

# 检查已安装的包
docker run --rm myrm/skill-sandbox:latest \
  uv pip list

# 查看镜像层信息
docker history myrm/skill-sandbox:latest

# 运行深度健康检查（验证所有关键依赖）
docker run --rm myrm/skill-sandbox:latest deep-health-check

# 检查容器的 seccomp 配置
docker inspect <container_id> | jq '.[0].HostConfig.SecurityOpt'

# 查看镜像详细分析（需要 dive 工具）
dive myrm/skill-sandbox:latest
```

---

## 相关文档

- [CHANGELOG.md](./CHANGELOG.md) - 版本更新日志
- [DISASTER_RECOVERY.md](./DISASTER_RECOVERY.md) - 灾难恢复策略和运维手册
- [Dockerfile](./Dockerfile) - 镜像构建定义
- [pyproject.toml](./pyproject.toml) - Python 依赖清单（uv 管理）

---

**联系**: MyrmAgent Team  
**最后更新**: 2026-05-31
