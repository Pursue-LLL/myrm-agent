# code_freshness/

## Overview
Three-state runtime code freshness verification (`fresh` / `stale` / `indeterminate`) and anti-tautological test methodology.
Compares active process launch time against source file modification timestamps on disk. Detects silent stale bytecode execution after hot deployments, articulates explicit reasons for indeterminate states, and applies non-tautological sentinel testing.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package Facade | Public re-exports of inspector and data models. | ✅ |
| `models.py` | Domain Models | Pydantic schemas for ModuleFreshnessEntry, RuntimeFreshnessReport, and FreshnessState. | ✅ |
| `inspector.py` | Core Inspector | RuntimeCodeFreshnessInspector comparing process lifetime vs on-disk filesystem mtime. | ✅ |
