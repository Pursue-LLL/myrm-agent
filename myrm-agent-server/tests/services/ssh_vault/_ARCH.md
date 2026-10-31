# tests/services/ssh_vault/

## Overview
Unit tests for SSH Vault and Host Configuration Discovery Service.

## File Index

| File | Role | Description |
|------|------|-------------|
| `test_ssh_vault.py` | Unit Test | Verifies `~/.ssh/config` parsing, host lookup, summary aggregation, and asynchronous TCP network probing. |
| `test_ssh_vault_readonly_gate.py` | Unit & Integration Test | Verifies the read-only gate, single-use break-glass tokens, policy APIs, and that no copy of a command or full token is kept or logged. |
| `test_ssh_vault_output_bound.py` | Unit Test | Verifies that a remote command's output and exit code come through, that a flood ends at the timeout with the `ssh` process gone and memory bounded, that output past the cap is cut with a note, and that a cancelled call stops `ssh`. |
| `conftest.py` | Fixture | `stand_in_ssh`: a program named `ssh` first on PATH that never connects and prints, floods or holds as the test says. |
