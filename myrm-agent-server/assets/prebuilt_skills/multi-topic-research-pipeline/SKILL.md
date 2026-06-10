---
name: multi-topic-research-pipeline
description: >-
  Fan-out research pipeline: investigate multiple topics in parallel, then
  cross-compare and synthesize findings into a unified report. Uses repeat_for
  to dynamically create one research task per selected topic.
version: 1.0.0
category: pipeline
tags:
  - pipeline
  - research
  - fan-out
  - multi-agent
allowed-tools: file_read_tool file_write_tool web_search_tool bash_code_execute_tool
pipeline_spec:
  discovery_questions:
    - group: "research_scope"
      group_label: "Research Scope"
      questions:
        - id: "topics"
          type: "multi-select"
          label: "Topics to research"
          options:
            - "Artificial Intelligence"
            - "Quantum Computing"
            - "Biotechnology"
            - "Renewable Energy"
            - "Blockchain / Web3"
            - "Robotics"
            - "Space Technology"
            - "Cybersecurity"
        - id: "research_depth"
          type: "select"
          label: "Research depth"
          options: ["Quick overview (1-2 pages)", "Standard analysis (3-5 pages)", "Deep dive (5+ pages)"]
    - group: "output_prefs"
      group_label: "Output Preferences"
      questions:
        - id: "perspective"
          type: "select"
          label: "Analysis perspective"
          options: ["Investment / Market", "Technical / Engineering", "Policy / Regulation", "Academic / Literature Review"]
        - id: "output_format"
          type: "select"
          label: "Final report format"
          options: ["Markdown Report", "Comparison Matrix + Executive Summary", "Slide Deck Outline"]
  role_templates:
    - role_id: "researcher"
      description: "Investigates a single topic: collects sources, analyses trends, identifies key players"
      required_skills: ["deep-research", "web-scraping"]
    - role_id: "synthesizer"
      description: "Cross-compares findings across topics and produces the unified deliverable"
      required_skills: ["deep-research", "creative-ideation"]
  task_graph_seed:
    - title_template: "Research: {_item}"
      description_template: >-
        Conduct a {research_depth} investigation of {_item} from a
        {perspective} perspective. Cover: current state, key players,
        recent breakthroughs, market size/trends, and risks/challenges.
      role: "researcher"
      parents: []
      repeat_for: "topics"
    - title_template: "Cross-comparison & Synthesis"
      description_template: >-
        Compare findings across all researched topics. Identify overlapping
        trends, synergies, and divergences. Produce a {output_format}
        highlighting the {perspective} angle.
      role: "synthesizer"
      parents: [0]
contract:
  steps:
    - "Phase 1 (parallel): Independent research on each selected topic"
    - "Phase 2 (sequential): Cross-comparison and unified synthesis"
  success_criteria: "Comprehensive multi-topic report with clear cross-comparison insights"
  estimated_duration_seconds: 7200
---

# Multi-Topic Research Pipeline

Fan-out research: select any number of topics, and the pipeline creates one
parallel research task per topic. Once all research tasks complete, a synthesis
task cross-compares findings and produces the final deliverable.

## How It Works

1. **Select topics** — pick 2-8 research areas from the list (or type custom ones)
2. **Each topic runs in parallel** — a dedicated researcher agent investigates independently
3. **Synthesis runs after all complete** — a synthesizer agent cross-compares and delivers the final report
