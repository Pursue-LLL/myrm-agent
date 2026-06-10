#!/usr/bin/env bash
# ============================================================================
# MyrmAgent installer (OSS bundle: myrm-agent-server + frontend + desktop)
# Run from myrm-agent repo root via: bash scripts/install.sh
# Windows (PowerShell): scripts/install.ps1 or irm https://myrmagent.ai/install.ps1 | iex
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck source=lib/resolve_agent_root.sh
source "${SCRIPT_DIR}/lib/resolve_agent_root.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

log_info() { echo -e "${CYAN}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "========================================================="
    echo "             MyrmAgent OSS bundle installer"
    echo "========================================================="
    echo -e "${NC}"
}

ensure_project_root() {
    if resolve_agent_paths "${PROJECT_ROOT}" 2>/dev/null; then
        return 0
    fi
    REPO_DIR="${MYRM_INSTALL_DIR:-$HOME/.myrm/myrm-agent}"
    REPO_URL="${MYRM_REPO_URL:-https://github.com/Pursue-LLL/myrm-agent.git}"
    log_info "Preparing install at ${REPO_DIR} ..."
    if [[ -d "${REPO_DIR}/myrm-agent-server" ]]; then
        cd "${REPO_DIR}"
        if [[ -d .git ]]; then
            git pull --ff-only 2>/dev/null || true
        fi
    else
        mkdir -p "$(dirname "${REPO_DIR}")"
        git clone --depth 1 "${REPO_URL}" "${REPO_DIR}"
        cd "${REPO_DIR}"
    fi
    PROJECT_ROOT="$(pwd)"
    export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.cargo/bin:$PATH"
    resolve_agent_paths "${PROJECT_ROOT}"
}

detect_os() {
    OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
    case "$OS" in
        darwin) OS="macos" ;;
        linux)  OS="linux" ;;
        mingw*|msys*|cygwin*|*_nt-*) OS="windows" ;;
        *)
            log_error "Unsupported OS: $OS"
            log_error "Windows (PowerShell): irm https://myrmagent.ai/install.ps1 | iex"
            exit 1
            ;;
    esac
    log_success "Detected OS: $OS"
}

detect_cn_network() {
    # Allow explicit override via environment
    if [[ "${MYRM_USE_CN_MIRROR:-0}" == "1" ]]; then
        return 0
    fi
    if [[ "${MYRM_NO_CN_MIRROR:-0}" == "1" ]]; then
        return 1
    fi
    # Respect user's existing mirror config
    if [[ -n "${UV_DEFAULT_INDEX:-}" ]]; then
        return 1
    fi
    # Dual detection: timezone hint + network probe
    local tz="${TZ:-}"
    if [[ -z "$tz" ]]; then
        if [[ -L /etc/localtime ]]; then
            tz="$(readlink /etc/localtime | sed 's|.*/zoneinfo/||')"
        else
            tz="$(cat /etc/timezone 2>/dev/null || true)"
        fi
    fi
    local tz_match=false
    case "$tz" in
        Asia/Shanghai|Asia/Chongqing|Asia/Harbin|CST-8) tz_match=true ;;
    esac
    if [[ "$tz_match" == "false" ]]; then
        return 1
    fi
    # Confirm with network probe (PyPI unreachable → likely behind GFW)
    if curl -fsS --connect-timeout 3 "https://pypi.org/simple/" -o /dev/null 2>/dev/null; then
        return 1
    fi
    return 0
}

setup_cn_mirrors() {
    export UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
    export BUN_CONFIG_REGISTRY="https://registry.npmmirror.com"
    export PLAYWRIGHT_DOWNLOAD_HOST="https://cdn.npmmirror.com/binaries/playwright"
    log_info "🇨🇳 检测到中国大陆网络，已自动切换至国内镜像加速"
    log_info "   PyPI: pypi.tuna.tsinghua.edu.cn"
    log_info "   npm:  registry.npmmirror.com"
    log_info "   Browser: cdn.npmmirror.com"
}

install_package_managers() {
    log_info "Checking uv and bun ..."
    if command -v uv &>/dev/null; then
        log_success "uv: $(uv --version)"
    else
        log_info "Installing uv ..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        log_success "uv installed"
    fi
    if command -v bun &>/dev/null; then
        log_success "bun: $(bun --version)"
    else
        log_info "Installing bun ..."
        curl -fsSL https://bun.sh/install | bash
        export PATH="$HOME/.bun/bin:$PATH"
        log_success "bun installed"
    fi
}

verify_harness_install() {
    local py=""
    if [[ -x "${SERVER_DIR}/.venv/bin/python" ]]; then
        py="${SERVER_DIR}/.venv/bin/python"
    elif [[ -x "${SERVER_DIR}/.venv/Scripts/python.exe" ]]; then
        py="${SERVER_DIR}/.venv/Scripts/python.exe"
    fi
    if [[ -z "${py}" ]]; then
        log_error "Missing .venv python after uv sync."
        exit 1
    fi
    if ! "${py}" -c "from myrm_agent_harness._distribution import assert_distribution_ready; assert_distribution_ready()"; then
        log_error "Harness distribution check failed. Ensure PyPI has myrm-agent-harness-core for this platform."
        exit 1
    fi
    log_success "Harness distribution OK."
}

setup_backend() {
    log_info "Backend (${SERVER_DIR}) ..."
    cd "${SERVER_DIR}"
    uv python install 3.13
    log_info "uv sync (core deps) ..."
    if ! uv sync; then
        log_error "Backend dependency sync failed."
        exit 1
    fi
    verify_harness_install
    log_info "Installing browser runtime (patchright) ..."
    uv run patchright install chromium 2>/dev/null || log_warn "Browser install skipped (non-fatal)."
    cd "${PROJECT_ROOT}"
    log_success "Backend ready."
}

setup_frontend() {
    log_info "Frontend (${FRONTEND_DIR}) ..."
    cd "${FRONTEND_DIR}"
    bun install
    bun run build
    cd "${PROJECT_ROOT}"
    log_success "Frontend ready."
}

setup_cli() {
    log_info "Registering global myrm CLI ..."
    BIN_DIR="$HOME/.local/bin"
    mkdir -p "${BIN_DIR}"
    SCRIPT_PATH="${SCRIPT_DIR}/myrm"
    chmod +x "${SCRIPT_PATH}"
    ln -sf "${SCRIPT_PATH}" "${BIN_DIR}/myrm"
    if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
        log_warn "Add ${BIN_DIR} to PATH"
    fi
    log_success "myrm CLI registered."
}

try_start_searxng() {
    if [[ "${MYRM_AUTO_START_SEARXNG:-0}" != "1" ]]; then
        log_info "Skipping SearXNG (set MYRM_AUTO_START_SEARXNG=1 to auto-start)."
        return 0
    fi
    if ! command -v docker &>/dev/null; then
        log_warn "Docker not found; cannot start SearXNG."
        return 0
    fi
    if [[ ! -f "${SERVER_DIR}/docker-compose.yaml" ]]; then
        return 0
    fi
    (cd "${SERVER_DIR}" && docker compose --profile search up -d) || \
        log_warn "SearXNG start failed — configure search in Settings"
}

main() {
    cd "${PROJECT_ROOT}"
    print_banner
    ensure_project_root
    detect_os
    if detect_cn_network; then
        setup_cn_mirrors
    fi
    install_package_managers
    setup_backend
    if [[ "${MYRM_INSTALL_SKIP_FRONTEND:-0}" != "1" ]]; then
        setup_frontend
    else
        log_info "Skipping frontend (MYRM_INSTALL_SKIP_FRONTEND=1)."
    fi
    setup_cli
    try_start_searxng
    echo -e "\n${GREEN}${BOLD}Install complete.${NC}"
    echo -e "Run: ${CYAN}${BOLD}myrm start${NC} → http://localhost:3000"
}

main
