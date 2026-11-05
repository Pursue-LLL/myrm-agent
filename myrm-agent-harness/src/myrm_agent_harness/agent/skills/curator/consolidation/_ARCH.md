# consolidation/

## Overview
Skill consolidation (umbrella merge). Groups skills that share a name prefix, lets an LLM judge each group, and merges the groups it approves into class-level umbrella skills.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports orchestrator and consolidation types | — |
| types.py | Core | SkillCluster, ConsolidationAction, ConsolidationPlan (with `failed_clusters`), ConsolidationReport, `occupied_names`, `is_consolidation_eligible` | ✅ |
| cluster_detector.py | Core | Groups skills sharing a name prefix into candidate clusters (the judge decides whether a family belongs together) | ✅ |
| judge.py | Core | LLM judge for merge strategy: the prompt spells out the judgment schema, the judge names the members that stay standalone, drops actions aimed at a taken umbrella name or an unknown target, and counts every cluster it has no usable verdict for | ✅ |
| executor.py | Core | Applies MERGE/CREATE_UMBRELLA/DEMOTE actions; leaves alone a source that is gone or no longer eligible; archives sources only after their content landed | ✅ |
| orchestrator.py | Core | SkillConsolidator: `propose` (filter → detect → judge, executes nothing) and `apply` (carries out a plan it is handed, no judge call) | ✅ |

## Judgment shape

The model client runs structured output in JSON mode, which guarantees valid JSON but not the fields, so the judge prompt carries the judgment schema (`PydanticOutputParser` format instructions). An action covers every cluster member except its target and the members the judge lists in `keep_standalone`; an action left with no member is dropped like KEEP.

## Untrusted targets

The LLM proposes every target name, so no name in a plan is trusted.

- `occupied_names(skills, reserved_names)` (types.py) is the set of case-folded names a new umbrella must not take: every skill the run may modify plus `reserved_names`, the skills the host keeps out of the run (the curator passes its protected and installed skills). Case is folded because a case-insensitive file system maps names that differ only in case to one skill directory.
- The judge drops a CREATE_UMBRELLA whose name is occupied and a MERGE/DEMOTE whose target is not one of the skills the run may modify, and logs a warning. The cluster is left as it is and counted in `failed_clusters`, so the preview never promises what the executor would refuse.
- The executor enforces the same at the side-effect boundary: it never saves an umbrella over an occupied name, and a MERGE/DEMOTE only writes into a candidate. The write backend reports a refused support-file write by returning a failure, so the executor checks the result and fails the action before it archives any source; support files already written stay in the target.

## A plan can be older than the run that applies it

`propose` and `apply` are separate calls, so a host can show the plan to the user and apply it later: what runs is the plan that was proposed, and the judge is not asked again (a model answers the same question differently from one call to the next). Skills change in between, so `apply` takes the skills as they are now and the executor re-checks eligibility (`is_consolidation_eligible`: not pinned, not evolution-locked, not archived, has a storage path) for every source the plan names. A source that is gone or has stopped being eligible counts as absent: it is neither absorbed nor archived, the rest of the action still runs, and an action left with no source fails with "No source skills found". `SkillCurator.apply_consolidation_plan` applies the host's current exemptions (`protected_names`, `installed_names`) the same way, so a skill bound to an agent or a scheduled job after the preview is not touched.

## Clusters the judge could not judge

An empty plan means "nothing to consolidate" only when every cluster was judged. A cluster with no usable verdict is counted in `ConsolidationPlan.failed_clusters`: the model call raised, its answer was not a judgment, or its action was dropped as an untrusted target. KEEP and an action with no member left are verdicts, not failures. The judge logs one warning with the counts. The server keeps the plan the preview returned, `failed_clusters` included, and executes exactly that plan.

`SkillCurator` swallows a failed consolidation pass and returns `None`, so the count travels inside the plan and the host decides what to do with it. The server turns an empty plan with `failed_clusters` into a 502; a plan with actions beside failed clusters is returned as it is.

## Module Dependencies

- `backends.skills.creation_protocols` (SkillWriteBackend)
- `langchain_core.language_models` (BaseChatModel)
- `langchain_core.output_parsers` (PydanticOutputParser)
