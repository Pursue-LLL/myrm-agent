---
name: competitive-analysis-pipeline
description: >-
  Competitive analysis pipeline: evaluate multiple competitors in parallel, then
  build a comparison matrix and strategic recommendations. Uses repeat_for to
  create one analysis task per selected competitor.
version: 1.0.0
category: pipeline
tags:
  - pipeline
  - competitive-analysis
  - strategy
  - fan-out
  - multi-agent
allowed-tools: file_read_tool file_write_tool web_search_tool bash_code_execute_tool
pipeline_spec:
  discovery_questions:
    - group: "context"
      group_label: "Analysis Context"
      questions:
        - id: "our_product"
          type: "text"
          label: "Your product / company name"
        - id: "competitors"
          type: "multi-select"
          label: "Competitors to analyze (select or type custom)"
          options:
            - "Competitor A"
            - "Competitor B"
            - "Competitor C"
            - "Competitor D"
            - "Competitor E"
        - id: "industry"
          type: "text"
          label: "Industry / market segment"
    - group: "focus"
      group_label: "Analysis Focus"
      questions:
        - id: "dimensions"
          type: "multi-select"
          label: "Comparison dimensions"
          options:
            - "Pricing & Packaging"
            - "Feature Set"
            - "Technical Architecture"
            - "User Experience"
            - "Go-to-Market Strategy"
            - "Community & Ecosystem"
        - id: "output_format"
          type: "select"
          label: "Deliverable format"
          options: ["Comparison Matrix + Report", "SWOT per Competitor", "Executive Brief"]
  role_templates:
    - role_id: "analyst"
      description: "Investigates a single competitor across the requested dimensions"
      required_skills: ["deep-research", "web-scraping"]
    - role_id: "strategist"
      description: "Builds the comparison matrix and strategic recommendations"
      required_skills: ["deep-research", "creative-ideation"]
  task_graph_seed:
    - title_template: "Analyze: {_item}"
      description_template: >-
        Conduct a thorough analysis of {_item} as a competitor to
        {our_product} in the {industry} space. Cover the following
        dimensions: {dimensions}. Gather pricing data, feature lists,
        public reviews, and any available technical details.
      role: "analyst"
      parents: []
      repeat_for: "competitors"
    - title_template: "Comparison Matrix & Strategic Recommendations"
      description_template: >-
        Synthesize all competitor analyses into a {output_format}.
        Highlight where {our_product} is stronger, where competitors
        lead, and provide actionable recommendations for competitive
        positioning in the {industry} market.
      role: "strategist"
      parents: [0]
contract:
  steps:
    - "Phase 1 (parallel): Independent analysis of each selected competitor"
    - "Phase 2 (sequential): Comparison matrix and strategic recommendations"
  success_criteria: "Actionable competitive intelligence with clear positioning guidance"
  estimated_duration_seconds: 5400
---

# Competitive Analysis Pipeline


## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

Parallel competitor deep-dive: analyze each competitor independently, then synthesize into a strategic comparison.

## How It Works

1. **Name your product** and select competitors
2. **Each competitor is analyzed in parallel** — pricing, features, UX, go-to-market
3. **Strategic synthesis** — comparison matrix with positioning recommendations
