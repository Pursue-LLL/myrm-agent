#!/usr/bin/env bash
# ============================================================================
# MyrmAgent installer (OSS bundle: myrm-agent-server + frontend + desktop)
# Run from myrm-agent repo root via: bash scripts/install.sh
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
        *) log_error "Unsupported OS: $OS"; exit 1 ;;
    esac
    log_success "Detected OS: $OS"
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

setup_backend() {
    log_info "Backend (${SERVER_DIR}) ..."
    cd "${SERVER_DIR}"
    uv python install 3.13
    log_info "uv sync (core deps) ..."
    if ! uv sync; then
        log_error "Backend dependency sync failed."
        exit 1
    fi
    log_info "Optional native extras ..."
    if ! uv pip install -e ".[advanced-tools]"; then
        log_warn "Advanced native extras failed; core server still usable."
    fi
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
    install_package_managers
    setup_backend
    setup_frontend
    setup_cli
    try_start_searxng
    echo -e "\n${GREEN}${BOLD}Install complete.${NC}"
    echo -e "Run: ${CYAN}${BOLD}myrm start${NC} → http://localhost:3000"
}

main
