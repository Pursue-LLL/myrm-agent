# providers/

## Overview
Toolkits Llms Providers module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Lazy registration facade: `ensure_providers_registered()` imports the provider modules once, keeping litellm out of the HTTP-server startup import path | — |
| minimax_image.py | Core | Custom LiteLLM provider for MiniMax image-01 model. Handles the translation | ✅ |
| yunshu.py | Core | Provides YunshuLLM. | ✅ |
