# context/

[INPUT]
- myrm_agent_harness.toolkits.context (POS: ContextBundle abstraction)
- myrm_agent_harness.toolkits.memory (POS: MemoryManager)
- app.core.memory.adapters.setup (POS: context binding resolver)

[OUTPUT]
- ContextAssemblyService: facade + binding assembly for agent runs
- ContextBundleService: bundle health probes and layout migration

[POS]
Server business layer for Context Bundle volume management. Workspace search uses
agentic grep/glob via FilesystemFileSearchMiddleware; no vector index service.

## File Index

| File | Role |
|------|------|
| `context_assembly.py` | Single facade+binding assembly for agent factory |
| `context_bundle_service.py` | Health probes, migration |
