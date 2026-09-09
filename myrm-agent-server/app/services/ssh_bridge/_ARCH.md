# app/services/ssh_bridge/

## Overview
Multi-Host SSH asset management, OpenSSH config parsing, command execution with safety gates, SFTP exploration, and AI Agent high-signal log distillation bridge.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Multi-Host SSH Operations, SFTP Explorer, and Agent Asset Bridge package exports. | ✅ |
| `models.py` | Models | Core data structures for SSH assets, parsed configs, command results, and SFTP metadata. | ✅ |
| `parser.py` | Parser | Robust OpenSSH `~/.ssh/config` parser extracting host directives. | ✅ |
| `manager.py` | Core Service | Host asset lifecycle manager supporting CRUD, tagging, and config import. | ✅ |
| `executor.py` | Core Service | High-risk command safety gating, execution timeout management, and SFTP transfer engine. | ✅ |
| `agent_bridge.py` | Agent Bridge | Unified AI Agent facade integrating `TerminalLogDistiller` for high-entropy output optimization. | ✅ |
