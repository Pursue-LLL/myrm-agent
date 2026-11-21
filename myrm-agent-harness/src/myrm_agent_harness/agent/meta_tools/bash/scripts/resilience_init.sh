#!/bin/bash

# Resilience Init Script
# Prepended to every command BashExecutor runs, foreground or background: non-interactive defaults, smart env
# injection for package managers, GitHub credentials for git over HTTPS, and a commit identity for sandboxes without one.

# -----------------------------------------------------------------------------
# Global Defense Environment Variables
# -----------------------------------------------------------------------------
# Force non-interactive mode to prevent Agent from hanging on prompts (e.g., npm init); a value the caller set stays
export CI="${CI:-1}"
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
        SKIP_ENV_VALIDATION=1 IGNORE_ENV_VALIDATION=1 command "$cmd_name" "$@"
    else
        command "$cmd_name" "$@"
    fi
}

# -----------------------------------------------------------------------------
# GitHub Credentials for git over HTTPS
# -----------------------------------------------------------------------------
# git's environment configuration reaches every git this command starts: `git -C`, a script it runs, a package manager
# fetching a git dependency. The helper below is scoped to the URL https://github.com, so another host, plain http and
# www.github.com never see the token. It hands out GITHUB_TOKEN (the credential pipeline sets it for the command) only
# while no other credential helper applies to that URL: git also tells every configured helper to store what it was
# given, and the keychain of a user must not keep a short-lived token. The lookup leaves out the helper's own entry by
# dropping the count of the environment configuration.
_register_github_credential_helper() {
    # One entry per shell, however often this script runs in it.
    [ -n "${_github_credential_helper_registered:-}" ] && return 0
    _github_credential_helper_registered=1
    local index="${GIT_CONFIG_COUNT:-0}"
    # shellcheck disable=SC2016 # the single quotes are deliberate: the shell git starts for the helper expands the variables
    local helper='!f() { [ "$1" = get ] && [ -n "${GITHUB_TOKEN:-}" ] && [ -z "$(unset GIT_CONFIG_COUNT; git config --get-urlmatch credential.helper https://github.com)" ] && printf "username=git\npassword=%s\n" "$GITHUB_TOKEN"; }; f'
    export "GIT_CONFIG_KEY_${index}=credential.https://github.com.helper" \
        "GIT_CONFIG_VALUE_${index}=${helper}" \
        "GIT_CONFIG_COUNT=$((index + 1))"
}
_register_github_credential_helper

# -----------------------------------------------------------------------------
# Commit Identity
# -----------------------------------------------------------------------------
# A sandbox without a git identity fails every commit with "Author identity unknown". The subcommands that write a
# commit get a fallback for whichever of name and email the repository, the user or the environment leaves unset.
git() {
    local -a global=()
    # The options before the subcommand come along unchanged; -C and --git-dir also decide whose configuration is read.
    while [ $# -gt 0 ]; do
        case "$1" in
            -C | -c | --git-dir | --work-tree | --namespace | --super-prefix)
                [ $# -ge 2 ] || break
                global+=("$1" "$2")
                shift 2
                ;;
            -*)
                global+=("$1")
                shift
                ;;
            *) break ;;
        esac
    done

    # The "+" form keeps an empty array from being an unbound variable under `set -u` in bash 3.2, the bash macOS ships.
    case "${1:-}" in
        commit | merge | cherry-pick | revert | rebase | am | pull | tag | notes)
            local -a identity=()
            command git ${global[@]+"${global[@]}"} config user.name >/dev/null 2>&1 || identity+=(-c user.name=myrm-agent)
            command git ${global[@]+"${global[@]}"} config user.email >/dev/null 2>&1 ||
                identity+=(-c user.email=myrm-agent@users.noreply.github.com)
            command git ${identity[@]+"${identity[@]}"} ${global[@]+"${global[@]}"} "$@"
            ;;
        *) command git ${global[@]+"${global[@]}"} "$@" ;;
    esac
}

# The package managers share the smart env injection above.
npm() { _inject_smart_env npm "$@"; }
npx() { _inject_smart_env npx "$@"; }
bun() { _inject_smart_env bun "$@"; }
bunx() { _inject_smart_env bunx "$@"; }
yarn() { _inject_smart_env yarn "$@"; }
pnpm() { _inject_smart_env pnpm "$@"; }
