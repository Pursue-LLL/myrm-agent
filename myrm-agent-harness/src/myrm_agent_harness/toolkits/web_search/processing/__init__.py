"""Search result processing, query constraint mapping, and citation resolution.

[INPUT]
- processing._explicit_params (POS: Agent explicit search constraints mapped onto provider parameters)
- processing.identifier_pinning (POS: Exact-phrase pinning of CVE ids and DOIs)
- processing.search_results_processor (POS: Search result post-processor)

[OUTPUT]
- Re-exports: combine_search_results_unified, search_results_to_documents, apply_domain_diversity_sort, describe_time_range_caveats, resolve_site_operators, resolve_time_range, split_site_operators, pin_structured_identifiers

[POS]
Subpackage entry for search post-processing and query constraint mapping.
"""

from myrm_agent_harness.toolkits.web_search.processing._explicit_params import (
    describe_time_range_caveats,
    resolve_site_operators,
    resolve_time_range,
    split_site_operators,
)
from myrm_agent_harness.toolkits.web_search.processing.identifier_pinning import pin_structured_identifiers
from myrm_agent_harness.toolkits.web_search.processing.search_results_processor import (
    apply_domain_diversity_sort,
    combine_search_results_unified,
    search_results_to_documents,
)

__all__ = [
    "apply_domain_diversity_sort",
    "combine_search_results_unified",
    "describe_time_range_caveats",
    "pin_structured_identifiers",
    "resolve_site_operators",
    "resolve_time_range",
    "search_results_to_documents",
    "split_site_operators",
]
