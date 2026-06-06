# context/

[INPUT]
- myrm_agent_harness.toolkits.context (POS: ContextBundle abstraction)
- myrm_agent_harness.toolkits.memory (POS: MemoryManager)
- myrm_agent_harness.toolkits.local_file_search (POS: LocalFileSearchEngine)
- app.services.local_file_search.service (POS: LocalFileSearchService)

[OUTPUT]
- ContextBundleService: Health probes, migration
[POS]
Server business layer for Context Bundle management and unified context search.
Orchestrates concurrent memory and workspace search using RRF fusion to provide
a single, unified cognitive interface for the Agent, eliminating tool redundancy.

## File Index

| File | Role |
|------|------|
| `context_assembly.py` | Single facade+binding assembly for agent factory |
| `context_bundle_service.py` | Health probes, migration |
| `context_search_service.py` | Unified memory + local file search (concurrent + RRF) |
| `context_search_deps.py` | FastAPI dependencies |