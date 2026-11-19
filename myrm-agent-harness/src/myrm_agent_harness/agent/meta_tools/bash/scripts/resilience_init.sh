#!/bin/bash

# Resilience Init Script
# Prepended to each command BashExecutor.execute runs: non-interactive defaults, smart env injection for package
# managers, GitHub credentials and a commit identity for git, and compact git status/diff output.

# -----------------------------------------------------------------------------
# Global Defense Environment Variables
# -----------------------------------------------------------------------------
# Force non-interactive mode to prevent Agent from hanging on prompts (e.g., npm init)
export CI=1
# Disable telemetry to speed up execution and reduce noise
export NEXT_TELEMETRY_DISABLED=1
export NUXT_TELEMETRY_DISABLED=1
export DO_NOT_TRACK=1
export GATSBY_TELEMETRY_DISABLED=1

# -----------------------------------------------------------------------------
# Smart Env Injection for Package Managers
# -----------------------------------------------------------------------------
_inject_smart_env() {
    local cmd_name="$1"
    shift
    local should_inject=0 arg

    for arg in "$@"; do
        if [[ "$arg" == "build" || "$arg" == "dev" || "$arg" == "tsc" || "$arg" == "lint" || "$arg" == "prisma" ]]; then
            should_inject=1
            break
        fi
    done

    if [ $should_inject -eq 1 ]; then
        SKIP_ENV_VALIDATION=1 IGNORE_ENV_VALIDATION=1 command $cmd_name "$@"
    else
        command $cmd_name "$@"
    fi
}

# -----------------------------------------------------------------------------
# GitHub Credential & Identity Injection (clone / push / commit)
# -----------------------------------------------------------------------------
# When GITHUB_TOKEN is present (injected by the credential pipeline), HTTPS
# GitHub clones and pushes authenticate automatically, and commits get a resolved
# identity even in freshly-provisioned sandboxes that have no global git config.

_git_is_https_github_remote() {
    case "$1" in
        https://github.com/* | http://github.com/* | https://www.github.com/*) return 0 ;;
        *) return 1 ;;
    esac
}

_git_has_existing_credentials() {
    [ -n "$(command git config --get credential.helper 2>/dev/null)" ] && return 0
    [ -f "$HOME/.git-credentials" ] && return 0
    return 1
}

_git_remote_url() {
    local branch remote
    branch=$(command git symbolic-ref --short HEAD 2>/dev/null)
    remote=$(command git config --get "branch.${branch}.remote" 2>/dev/null)
    [ -z "$remote" ] && remote="origin"
    command git remote get-url "$remote" 2>/dev/null
}

_git_resolve_identity() {
    local name email login cached cname cemail cache_file
    name=$(command git config --get user.name 2>/dev/null) || name=""
    email=$(command git config --get user.email 2>/dev/null) || email=""
    if [ -z "$name" ] || [ -z "$email" ]; then
        if [ -n "${GITHUB_TOKEN:-}" ]; then
            cache_file="${TMPDIR:-/tmp}/myrm_gh_identity"
            if [ -f "$cache_file" ]; then
                cached=$(cat "$cache_file")
                cname="${cached%%|*}"
                cemail="${cached#*|}"
                [ -z "$name" ] && name="$cname"
                [ -z "$email" ] && email="$cemail"
            fi
            if [ -z "$name" ] || [ -z "$email" ]; then
                login=$(curl -fsSL --max-time 5 -H "Authorization: Bearer ${GITHUB_TOKEN}" \
                    https://api.github.com/user 2>/dev/null \
                    | grep -o '"login":"[^"]*"' | head -n 1 | cut -d'"' -f4)
                if [ -n "$login" ]; then
                    [ -z "$name" ] && name="$login"
                    [ -z "$email" ] && email="${login}@users.noreply.github.com"
                    printf '%s|%s' "$name" "$email" > "$cache_file" 2>/dev/null || true
                fi
            fi
        fi
    fi
    [ -z "$name" ] && name="myrm-agent"
    [ -z "$email" ] && email="myrm-agent@users.noreply.github.com"
    printf '%s|%s' "$name" "$email"
}

# Runs git with the GitHub token when the remote URL in $1 is a plain HTTPS GitHub URL and the sandbox has no
# credentials of its own; otherwise runs git untouched. The rest of the arguments are the whole git command line.
_git_with_github_credentials() {
    local url="$1"
    shift
    if [ -n "${GITHUB_TOKEN:-}" ] && _git_is_https_github_remote "$url" && ! _git_has_existing_credentials; then
        # The token is referenced via the environment (never inlined), so it
        # cannot inject shell metacharacters into the credential helper. The
        # helper is host-scoped: it only answers for github.com hosts, so the
        # token is never handed to third-party HTTPS git servers the agent may
        # clone from or push to (e.g. a self-hosted GitLab remote or a raw HTTPS URL).
        # shellcheck disable=SC2016 # the single quotes are deliberate: git's helper shell expands ${GITHUB_TOKEN}
        command git -c 'credential.helper=!f() { host=""; while IFS= read -r line; do case "$line" in host=*) host="${line#host=}";; esac; done; if [ "$host" = "github.com" ] || [ "$host" = "www.github.com" ]; then echo username=git; echo password="${GITHUB_TOKEN}"; fi; }; f' "$@"
    else
        command git "$@"
    fi
}

_git_clone() {
    local arg url=""
    for arg in "$@"; do
        if _git_is_https_github_remote "$arg"; then
            url="$arg"
            break
        fi
    done
    _git_with_github_credentials "$url" "$@"
}

_git_push() {
    local url=""
    # Looking up the remote spawns three git processes, so it is skipped when there is no token to hand out.
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        # A repository without that remote makes the lookup fail, which must not end a script running under `set -e`.
        url=$(_git_remote_url) || url=""
    fi
    _git_with_github_credentials "$url" "$@"
}

_git_commit() {
    if ! command git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        command git "$@"
        return $?
    fi
    if ! command git config --get user.name >/dev/null 2>&1 || ! command git config --get user.email >/dev/null 2>&1; then
        local ident name email
        ident=$(_git_resolve_identity)
        name="${ident%%|*}"
        email="${ident#*|}"
        command git -c "user.name=${name}" -c "user.email=${email}" "$@"
        return $?
    fi
    command git "$@"
}

# -----------------------------------------------------------------------------
# Command Hijacking
# -----------------------------------------------------------------------------

# The clone, push and commit helpers hand the whole argument list, subcommand included, on to git.
git() {
    local subcommand="${1:-}" arg
    if [ "$subcommand" = "clone" ]; then
        _git_clone "$@"
    elif [ "$subcommand" = "status" ]; then
        local has_format_arg=0
        for arg in "$@"; do
            if [ "$arg" = "--short" ] || [ "$arg" = "-s" ] || [ "$arg" = "--porcelain" ]; then
                has_format_arg=1
                break
            fi
        done
        if [ $has_format_arg -eq 0 ]; then
            shift
            # Force English locale to ensure predictable output if any non-porcelain text leaks
            LC_ALL=C command git status --porcelain -b -uall "$@"
            local exit_code=$?
            if [ $exit_code -eq 0 ]; then
                echo "[System Note: Command was automatically optimized for machine readability]"
            fi
            return $exit_code
        else
            command git "$@"
        fi
    elif [ "$subcommand" = "diff" ]; then
        shift
        local has_stat_arg=0
        local has_no_compact_arg=0
        local diff_args=()
        for arg in "$@"; do
            if [ "$arg" = "--stat" ] || [ "$arg" = "--numstat" ] || [ "$arg" = "--shortstat" ] || [ "$arg" = "--name-only" ]; then
                has_stat_arg=1
            fi
            if [ "$arg" = "--no-compact" ]; then
                has_no_compact_arg=1
            else
                diff_args+=("$arg")
            fi
        done

        # The "+" form keeps an empty array from being an unbound variable under `set -u` in bash 3.2, the bash macOS ships.
        if [ $has_stat_arg -eq 0 ] && [ $has_no_compact_arg -eq 0 ]; then
            echo "[System Note: Command was automatically optimized. Showing --stat summary first.]"
            LC_ALL=C command git diff --stat ${diff_args[@]+"${diff_args[@]}"}
            echo ""
            echo "--- Changes ---"
            LC_ALL=C command git diff ${diff_args[@]+"${diff_args[@]}"}
            return $?
        else
            LC_ALL=C command git diff ${diff_args[@]+"${diff_args[@]}"}
        fi
    elif [ "$subcommand" = "push" ]; then
        _git_push "$@"
    elif [ "$subcommand" = "commit" ]; then
        _git_commit "$@"
    else
        command git "$@"
    fi
}

# The package managers share the smart env injection above.
npm() { _inject_smart_env npm "$@"; }
npx() { _inject_smart_env npx "$@"; }
bun() { _inject_smart_env bun "$@"; }
bunx() { _inject_smart_env bunx "$@"; }
yarn() { _inject_smart_env yarn "$@"; }
pnpm() { _inject_smart_env pnpm "$@"; }
