# context/

## File Index

| File | Role |
|------|------|
| `context_assembly.py` | Single facade+binding assembly for agent factory |
| `context_bundle_service.py` | Health probes, migration |
| `context_search_service.py` | Unified memory + local file search (RRF) |
| `context_search_deps.py` | FastAPI dependencies |
| `context_search_tools.py` | Agent `context_search_tool` factory |

## Dependencies

- `myrm_agent_harness.toolkits.context`
- `app.services.local_file_search.service`
