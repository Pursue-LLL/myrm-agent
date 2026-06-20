#!/usr/bin/env bash
# Shared CN mirror detection and setup for install.sh, myrm, and dev scripts.

detect_cn_network() {
    if [[ "${MYRM_USE_CN_MIRROR:-0}" == "1" ]]; then
        return 0
    fi
    if [[ "${MYRM_NO_CN_MIRROR:-0}" == "1" ]]; then
        return 1
    fi
    if [[ -n "${UV_DEFAULT_INDEX:-}" ]]; then
        return 1
    fi
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
    if curl -fsS --connect-timeout 3 "https://pypi.org/simple/" -o /dev/null 2>/dev/null; then
        return 1
    fi
    return 0
}

setup_cn_mirrors() {
    export UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
    export BUN_CONFIG_REGISTRY="https://registry.npmmirror.com"
    export PLAYWRIGHT_DOWNLOAD_HOST="https://cdn.npmmirror.com/binaries/playwright"
    if declare -f log_info >/dev/null 2>&1; then
        log_info "🇨🇳 检测到中国大陆网络，已自动切换至国内镜像加速"
        log_info "   PyPI: pypi.tuna.tsinghua.edu.cn"
        log_info "   npm:  registry.npmmirror.com"
        log_info "   Browser: cdn.npmmirror.com"
    fi
}

apply_cn_mirrors_if_needed() {
    if detect_cn_network; then
        setup_cn_mirrors
    fi
}
