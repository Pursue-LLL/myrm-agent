"""Sub-agent subsystem — lifecycle management and configuration loading.

Configuration Architecture:
- Framework layer: Provides loading mechanism (config_loader.py)
- Business layer: Provides configuration content and policy

Configuration Loading:
- Business layer explicitly provides configuration directory path
- Framework layer loads and validates YAML files
- See business layer configs/subagents/_ARCH.md for format details

[INPUT]
- (none)

[OUTPUT]
- (none — consumers import the submodules by path)

[POS]
Sub-agent subsystem — lifecycle management and configuration loading.
"""
