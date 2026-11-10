/**
 * JIT 一键编队的蓝图模板
 *
 * 每个成员的 tools 必须是 harness 注册的工具全名，且不能为空（空数组 = 继承父级全部工具）；
 * 由 server tests/architecture/test_blueprint_template_tools_parity.py 校验。
 */
export const BLUEPRINT_TEMPLATES = [
  {
    id: 'research_squad',
    subagents: {
      web_researcher: {
        display_name: 'Information Retrieval Specialist',
        system_prompt:
          'You are an information retrieval specialist responsible for using browsers and search engines to gather and summarize in-depth information from across the web.',
        tools: [
          'web_search_tool',
          'web_fetch_tool',
          'browser_navigate_tool',
          'browser_inspect_tool',
          'browser_snapshot_tool',
          'browser_interact_tool',
          'browser_extract_tool',
        ],
        max_turns: 10,
        context_mode: 'fork',
      },
      data_analyst: {
        display_name: 'Data Synthesis Analyst',
        system_prompt:
          'You are a data analysis expert responsible for cross-validating, deduplicating, and deeply synthesizing retrieved information.',
        tools: ['file_read_tool', 'grep_tool', 'glob_tool', 'web_search_tool', 'web_fetch_tool'],
        max_turns: 5,
        context_mode: 'fork',
      },
    },
  },
  {
    id: 'code_audit_squad',
    subagents: {
      security_expert: {
        display_name: 'Security Defense Expert',
        system_prompt:
          'You are a top code security expert responsible for auditing code vulnerabilities (XSS, injection, privilege escalation, etc.).',
        tools: ['file_read_tool', 'grep_tool', 'glob_tool', 'bash_code_execute_tool'],
        max_turns: 10,
        context_mode: 'fork',
      },
      perf_expert: {
        display_name: 'Performance Optimization Master',
        system_prompt:
          'You are a performance optimization master responsible for finding O(n^2) complexity, memory leaks, redundant rendering, and other performance defects.',
        tools: ['file_read_tool', 'grep_tool', 'glob_tool', 'bash_code_execute_tool'],
        max_turns: 10,
        context_mode: 'fork',
      },
    },
  },
];
