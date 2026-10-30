# search/

## Overview
Skill search module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Skill search module. | — |
| config/synonyms.yaml | Config | Single source of truth for English/Chinese synonyms and typo corrections. | — |
| config_loader.py | Config | Loads `config/synonyms.yaml`; a missing file yields empty mappings with a warning. | ✅ |
| engine.py | Core | BM25 + regex skill search over available, model-invocable skills; all MCP skills index every tool name and truncated tool description; supports `select:name` exact lookup and `+term` required-term filters; index text and queries share one `snake_case`→words rule (`_split_snake_case`); QueryExpander on by default. | ✅ |
| hybrid_engine.py | Core | Hybrid search (BM25 + embedding, RRF); exact/required-term grammar stays lexical. Lazy-imports numpy; missing numpy raises RuntimeError pointing to `[retrieval]`. | ✅ |
| query_expansion.py | Core | Adds query variants (typo-corrected, synonyms) without rewriting the caller's text; queries already in the "concept/translation/synonym" `/` format skip synonym expansion. | ✅ |
| synonym_expander.py | Core | Synonym expansion with whole-word English matching; mappings come only from `config/synonyms.yaml`. | ✅ |
| types.py | Config | Provides SearchMetadata, SkillSearchResult. | ✅ |
| typo_corrector.py | Core | Case-insensitive typo corrections loaded from `config/synonyms.yaml`. | ✅ |

## Key Dependencies

- `backends`
- `toolkits`
- Optional: `myrm-agent-harness[retrieval]` (numpy for vector index paths in `hybrid_engine.py`)
