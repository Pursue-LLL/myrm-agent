#!/usr/bin/env python
"""Myrm CLI - Configuration management tool

Usage:
    python myrm_cli.py config validate
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(override=False)
load_dotenv(".env.local", override=False)

from app.config.pre_flight import preflight_check_config  # noqa: E402


def cmd_config_validate() -> int:
    """Validate configuration without restarting

    Returns:
        int: Exit code (0 if valid, 1 if errors)
    """
    print("[CONFIG] Validating configuration from .env and config files...")

    result = preflight_check_config()

    if result.infos:
        for info in result.infos:
            print(f"[CONFIG] ℹ️  {info}")

    if result.warnings:
        for warning in result.warnings:
            print(f"[CONFIG] ⚠️  Warning: {warning}")

    if result.errors:
        for error in result.errors:
            print(f"[CONFIG] ✗ Error: {error}")
        print("\nConfiguration is invalid. Fix the errors above and try again.\n")
        return 1

    print("\nConfiguration is valid. Restart the server to apply changes.\n")
    return 0


def main() -> int:
    """CLI entry point"""
    if len(sys.argv) < 2:
        print("Usage: python myrm_cli.py <command> [args]")
        print("\nCommands:")
        print("  config validate    Validate configuration without restarting")
        return 1

    command = sys.argv[1]

    if command == "config":
        if len(sys.argv) < 3:
            print("Usage: python myrm_cli.py config <subcommand>")
            print("\nSubcommands:")
            print("  validate    Validate configuration")
            return 1

        subcommand = sys.argv[2]
        if subcommand == "validate":
            return cmd_config_validate()
        else:
            print(f"Unknown config subcommand: {subcommand}")
            return 1
    else:
        print(f"Unknown command: {command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
