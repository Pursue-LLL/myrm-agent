# Opt-in wall-clock markers on stderr. The E2E runtime sets MYRM_STACK_STAGE_TRACE=1 on the
# private-backend ensure call to learn where its startup time goes; other callers see nothing.
# Sourced by dev-stack.sh and backend_bg.sh (dev.sh sources the latter on its own).
_stack_stage() {
  if [[ "${MYRM_STACK_STAGE_TRACE:-}" == "1" ]]; then
    echo "STACK_STAGE: $1 wall=$(date +%s)" >&2
  fi
}
