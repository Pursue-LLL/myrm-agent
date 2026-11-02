# consolidation/

## Overview
Skill consolidation (umbrella merge). Groups skills that share a name prefix, lets an LLM judge each group, and merges the groups it approves into class-level umbrella skills.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports orchestrator and consolidation types | — |
| types.py | Core | SkillCluster, ConsolidationAction, ConsolidationPlan (with `failed_clusters`), ConsolidationReport, `occupied_names` | ✅ |
| cluster_detector.py | Core | Groups skills sharing a name prefix into candidate clusters (the judge decides whether a family belongs together) | ✅ |
| judge.py | Core | LLM judge for merge strategy: the prompt spells out the judgment schema, the judge names the members that stay standalone, drops actions aimed at a taken umbrella name or an unknown target, and counts every cluster it has no usable verdict for | ✅ |
| executor.py | Core | Applies MERGE/CREATE_UMBRELLA/DEMOTE actions; archives sources only after their content landed | ✅ |
| orchestrator.py | Core | SkillConsolidator pipeline: detect → judge → execute (dry-run support) | ✅ |

## Judgment shape

The model client runs structured output in JSON mode, which guarantees valid JSON but not the fields, so the judge prompt carries the judgment schema (`PydanticOutputParser` format instructions). An action covers every cluster member except its target and the members the judge lists in `keep_standalone`; an action left with no member is dropped like KEEP.

## Untrusted targets

The LLM proposes every target name, so no name in a plan is trusted.

- `occupied_names(skills, reserved_names)` (types.py) is the set of case-folded names a new umbrella must not take: every skill the run may modify plus `reserved_names`, the skills the host keeps out of the run (the curator passes its protected and installed skills). Case is folded because a case-insensitive file system maps names that differ only in case to one skill directory.
- The judge drops a CREATE_UMBRELLA whose name is occupied and a MERGE/DEMOTE whose target is not one of the skills the run may modify, and logs a warning. The cluster is left as it is and counted in `failed_clusters`, so the preview never promises what the executor would refuse.
- The executor enforces the same at the side-effect boundary: it never saves an umbrella over an occupied name, and a MERGE/DEMOTE only writes into a candidate. The write backend reports a refused support-file write by returning a failure, so the executor checks the result and fails the action before it archives any source; support files already written stay in the target.

## Clusters the judge could not judge

An empty plan means "nothing to consolidate" only when every cluster was judged. A cluster with no usable verdict is counted in `ConsolidationPlan.failed_clusters`: the model call raised, its answer was not a judgment, or its action was dropped as an untrusted target. KEEP and an action with no member left are verdicts, not failures. The judge logs one warning with the counts. The summary of an empty plan with failures says so instead of "well-organized"; the summary of a plan with actions never mentions failures, because the server's plan token hashes it and a transient failure must not change the plan the user confirms.

`SkillCurator` swallows a failed consolidation pass and returns `None`, so the count travels inside the plan and the host decides what to do with it. The server turns an empty plan with `failed_clusters` into a 502; a plan with actions beside failed clusters is returned as it is.

## Module Dependencies

- `backends.skills.creation_protocols` (SkillWriteBackend)
- `langchain_core.language_models` (BaseChatModel)
- `langchain_core.output_parsers` (PydanticOutputParser)
