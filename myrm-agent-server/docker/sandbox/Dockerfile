# Myrm Skill Sandbox v1.3.0
# 统一的生产级沙箱镜像：开发、测试、生产使用同一镜像
#
# 设计原则：
# - 统一环境策略：确保各环境依赖版本完全一致（uv.lock）
# - 功能完整性：预装 90% 技能所需的依赖，开箱即用
# - 性能优先：预装依赖，避免运行时动态安装
# - 安全隔离：Docker 默认 seccomp + ReadonlyRootfs + 非 root 用户
#
# 预装内容：
# - 运行时：Python 3.14 + Node.js 20 + Bun 1.3.11
# - Python 包：pandas, numpy, matplotlib, openpyxl, python-docx, python-pptx 等 70+ 个
# - npm 包：pptxgenjs, sharp, react 等 5 个全局包
# - 系统工具：ripgrep, fd, git, sqlite, poppler 等 20+ 个
# - 字体：Noto CJK（中日韩）+ Noto Color Emoji + Liberation（Latin）
# - matplotlib：默认 sans-serif 指向 Noto CJK（中文图表不豆腐块），构建时 fail-fast 验证
# - 健康检查：deep-health-check 脚本（验证关键依赖）
#
# 构建特性：
# - 多阶段构建：分离构建和运行时环境
# - uv 包管理：lockfile 确保依赖一致性
# - 依赖分层：按变化频率分层，提升缓存命中率
# - BuildKit 缓存挂载：加速依赖安装
# - 性能预热：预导入和编译常用模块（pandas、numpy、matplotlib）
# - 多架构支持：linux/amd64 + linux/arm64

ARG UV_VERSION=0.9.15
ARG BUN_VERSION=1.3.11

# ============================================================================
# Stage 1: Builder - 构建环境
# ============================================================================
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv-bin
FROM python:3.14-slim AS builder

# 设置构建环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1

COPY --from=uv-bin /uv /usr/local/bin/uv

# 安装构建依赖（在 builder 阶段，不会进入最终镜像）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖到临时位置
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project \
    && mkdir -p /install/lib/python3.14 \
    && cp -r .venv/lib/python3.14/site-packages /install/lib/python3.14/site-packages

# ============================================================================
# Stage 2: Runtime - 运行时环境
# ============================================================================
FROM python:3.14-slim AS runtime

LABEL maintainer="MyrmAgent"
LABEL description="Sandbox environment for executing skill code"
LABEL version="1.0.0"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NODE_VERSION=20 \
    NPM_CONFIG_PREFIX=/workspace/.npm-global \
    NODE_PATH=/usr/lib/node_modules \
    PATH=/workspace/.npm-global/bin:$PATH \
    PYTHONPATH=/usr/local/lib/python3.14/site-packages \
    MPLBACKEND=Agg \
    MATPLOTLIBRC=/opt/mpl-config/matplotlibrc \
    MPLCONFIGDIR=/tmp/matplotlib

# Layer 1: 创建用户（很少变化）
RUN groupadd -r sandbox && useradd -r -g sandbox -m -d /home/sandbox sandbox \
    && mkdir -p /home/sandbox/.cache/uv \
    && chown -R sandbox:sandbox /home/sandbox

# Layer 2: 系统依赖（偶尔变化）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    curl \
    ca-certificates \
    unzip \
    unrar-free \
    p7zip-full \
    gnupg \
    bc \
    sqlite3 \
    # 搜索工具
    ripgrep \
    fd-find \
    # 图像处理运行时库
    libpng16-16 \
    libjpeg62-turbo \
    libfreetype6 \
    # PDF 处理
    poppler-utils \
    # CJK + Emoji + Latin 字体（浏览器截图/PDF 导出/matplotlib 渲染）
    fontconfig \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-liberation \
    # 版本控制
    git \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/* \
    && (ln -sf /usr/bin/fdfind /usr/bin/fd || true)

# Layer 3: Node.js 和 Bun（偶尔变化）
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

ARG BUN_VERSION
ENV BUN_INSTALL=/usr/local
RUN curl -fsSL https://bun.sh/install | bash -s -- bun-v${BUN_VERSION}

# Layer 4: npm 全局包（偶尔变化）
RUN --mount=type=cache,target=/root/.npm \
    NPM_CONFIG_PREFIX= npm install -g \
    pptxgenjs@4.0.1 \
    sharp@0.34.5 \
    react@19.2.4 \
    react-dom@19.2.4 \
    react-icons@5.6.0

# Layer 5: 从 builder 复制 Python 依赖（频繁变化）
COPY --from=builder /install /usr/local

COPY --from=uv-bin /uv /usr/local/bin/uv

# Layer 6: matplotlib CJK 默认配置
# MATPLOTLIBRC 直接指向 rc 文件，绕过 get_configdir 可写性回退，只读 rootfs 下仍可靠加载 CJK 配置
# MPLCONFIGDIR 把字体缓存（fontlist.json）落到可写 tmpfs /tmp，避免只读 rootfs 下每次执行重建字体缓存
COPY matplotlibrc /opt/mpl-config/matplotlibrc

# Layer 6.5: 性能预热 + matplotlib CJK 字体 fail-fast 验证
# 默认 sans-serif 必须解析到 Noto CJK（而非 DejaVu fallback），否则构建失败
RUN python -c "import pandas, numpy, matplotlib, openpyxl, PIL, pypdf; print('✅ Core packages preloaded')" \
    && python -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm; f = fm.findfont(fm.FontProperties(family='sans-serif')); assert 'NotoSansCJK' in f or 'NotoSerifCJK' in f, f'CJK font not active: {f}'; fig, ax = plt.subplots(); ax.set_title('中文渲染验证'); ax.plot([1, 2, 3]); fig.savefig('/tmp/_mpl_verify.png'); print('✅ matplotlib CJK verified:', f)" \
    && python -m compileall -q /usr/local/lib/python3.14/site-packages/pandas \
    && python -m compileall -q /usr/local/lib/python3.14/site-packages/numpy \
    && python -m compileall -q /usr/local/lib/python3.14/site-packages/matplotlib

# Layer 7: 创建工作目录
WORKDIR /workspace
RUN mkdir -p /workspace/.npm-global \
    && chown -R sandbox:sandbox /workspace

COPY --chmod=755 deep_health_check.py /usr/local/bin/deep-health-check

RUN rm -rf /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    && find /usr/share/locale -mindepth 1 -maxdepth 1 ! -name 'en*' -exec rm -rf {} + \
    && rm -rf /tmp/* /var/tmp/*

# 切换到非 root 用户
USER sandbox

# 健康检查：轻量化验证（检查 Python 运行时和 uv 工具可用性）
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" && uv --version > /dev/null || exit 1

# 默认命令
CMD ["python", "-c", "print('Sandbox ready')"]
