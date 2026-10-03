"""Four-dimension concept extraction prompt for wiki compilation.

[INPUT]
- (pure constants; extends the default extract_concepts_prompt_template contract)

[OUTPUT]
- FOUR_DIMENSION_EXTRACT_PROMPT: vault-global concept routing prompt

[POS]
Vault-global four-dimension classification prompt injected through the existing
WikiCompileConfig.extract_concepts_prompt_template extension point (harness zero-change).
Every compiled concept name is routed under one of the four dimensions:
Projects / Knowledge / Methods / Comparisons.
"""

from __future__ import annotations

FOUR_DIMENSION_EXTRACT_PROMPT = (
    "Extract key concepts from the following document. Return a JSON array of objects.\n"
    "Each object MUST have these fields:\n"
    '- "name": concept name with logical folder path (e.g., "Knowledge/Rust/Ownership")\n'
    '- "definition": brief definition of the concept\n'
    '- "related_concepts": array of related concept names from the same document\n'
    '- "mentions": integer count of how many times the concept is actually mentioned in the document\n'
    "CRITICAL ROUTING RULES:\n"
    "The first path segment of every concept name MUST be one of these four dimensions:\n"
    '- "Projects/...": engineering progress, milestones, delivery decisions, and work items.\n'
    '- "Knowledge/...": domain facts, concept definitions, and technical principles.\n'
    '- "Methods/...": reusable methods, lessons learned, how-to procedures, and checklists.\n'
    '- "Comparisons/...": tool comparisons, trade-off analyses, and alternative evaluations.\n'
    "Correct routing examples:\n"
    '- "Projects/WikiGate/HumanInLoopPublish" for a shipped engineering milestone.\n'
    '- "Knowledge/Karpathy/FiveLayerArchitecture" for a learned architecture fact.\n'
    '- "Methods/Engineering/PublishGateChecklist" for a reusable practice.\n'
    '- "Comparisons/ObsidianVsNotion" for a tooling trade-off decision.\n'
    "Use forward slashes '/' for paths. Only when a concept truly fits none of the four "
    "dimensions, use 'Uncategorized/ConceptName'.\n"
    "Output ONLY the JSON array, no extra text."
)

__all__ = ["FOUR_DIMENSION_EXTRACT_PROMPT"]
