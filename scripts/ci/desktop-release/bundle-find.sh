#!/usr/bin/env bash
# GNU find on GHA Windows (--noprofile puts System32 find.exe on PATH).
if [[ -x /usr/bin/find ]]; then
  exec /usr/bin/find "$@"
fi
exec find "$@"
