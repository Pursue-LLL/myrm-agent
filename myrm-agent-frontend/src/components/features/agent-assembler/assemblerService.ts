/**
 * Client-side Service for Visual Modular Agent Assembler.
 *
 * [INPUT] assemblerTypes
 * [OUTPUT] assemblerService: API integration with graceful offline fallbacks for validation and sandbox dry-run.
 * [POS] src/components/features/agent-assembler/assemblerService.ts
 */

import type {
  AssemblyBlueprint,
  AssemblyValidationResult,
  CapabilityBlock,
  SandboxDryRunRequest,
  SandboxDryRunResult,
} from './assemblerTypes';

export const DEFAULT_BLOCK_CATALOG: CapabilityBlock[] = [
  {
    id: 'brain-sonnet',
    category: 'brain',
    name: 'Claude 3.7 Sonnet',
    description: 'High-reasoning brain model with dynamic thinking budget control.',
    enabled: true,
    config: {
      primary_model: 'claude-3-7-sonnet',
      temperature: 0.2,
      fallback_model: 'gpt-4o-mini',
    },
  },
  {
    id: 'brain-gpt4o',
    category: 'brain',
    name: 'GPT-4o Omnipresent',
    description: 'Balanced intelligence and high-throughput execution brain.',
    enabled: true,
    config: { primary_model: 'gpt-4o', temperature: 0.3 },
  },
  {
    id: 'persona-engineer',
    category: 'persona',
    name: 'Principal Full-Stack Engineer',
    description: 'Clean architecture, zero any types, test-driven craftsmanship.',
    enabled: true,
    config: {
      prompt_template: 'You are a World-Class Software Architect. Deliver production-grade, tested code.',
      persona_signature: 'Engineering Excellence First',
    },
  },
  {
    id: 'persona-analyst',
    category: 'persona',
    name: 'Data & Research Analyst',
    description: 'Evidence-based reasoning, citation verification and data synthesis.',
    enabled: true,
    config: {
      prompt_template: 'You are a Senior Quantitative Analyst. Always verify citations and compute precisely.',
      persona_signature: 'Evidence & Grounded Truth',
    },
  },
  {
    id: 'tools-core-dev',
    category: 'tools',
    name: 'Core Development Toolset',
    description: 'File read/write, bash execution, AST analysis tools.',
    enabled: true,
    config: {
      tool_names: ['read_file', 'write_to_file', 'run_command', 'replace_file_content'],
      has_python_microtool: true,
    },
  },
  {
    id: 'skills-github-ci',
    category: 'skills',
    name: 'GitHub Actions & CI Mastery',
    description: 'Pre-compiled domain skill for CI/CD workflow crafting.',
    enabled: true,
    config: { skill_slug: 'github-actions-ci', version: '1.2.0' },
  },
  {
    id: 'memory-hierarchical',
    category: 'memory',
    name: 'Hierarchical Vector & Graph Memory',
    description: 'Multi-tier semantic retrieval and episodic recall.',
    enabled: true,
    config: { enable_semantic: true, enable_episodic: true, isolation_scope: 'project' },
  },
  {
    id: 'sandbox-strict',
    category: 'sandbox',
    name: 'Restricted Sandbox Container',
    description: 'Read-only root, safe directory writes, 30s timeout cap.',
    enabled: true,
    config: { timeout_seconds: 30, allow_net: true, write_scoped: true },
  },
];

class AssemblerService {
  private readonly baseUrl = '/api/v1/agents/assembler';

  async getBlockCatalog(): Promise<CapabilityBlock[]> {
    try {
      const res = await fetch(`${this.baseUrl}/block-catalog`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        const data = (await res.json()) as CapabilityBlock[];
        return data;
      }
    } catch {
      // Fallback to static catalog on connection failure
    }
    return DEFAULT_BLOCK_CATALOG;
  }

  async validateAssembly(blueprint: AssemblyBlueprint): Promise<AssemblyValidationResult> {
    try {
      const res = await fetch(`${this.baseUrl}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(blueprint),
      });
      if (res.ok) {
        const data = (await res.json()) as AssemblyValidationResult;
        return data;
      }
    } catch {
      // Offline fallback validation
    }

    return this.fallbackValidate(blueprint);
  }

  async dryRunAssembly(req: SandboxDryRunRequest): Promise<SandboxDryRunResult> {
    try {
      const res = await fetch(`${this.baseUrl}/dry-run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (res.ok) {
        const data = (await res.json()) as SandboxDryRunResult;
        return data;
      }
    } catch {
      // Offline fallback dry-run
    }

    return this.fallbackDryRun(req);
  }

  private fallbackValidate(blueprint: AssemblyBlueprint): AssemblyValidationResult {
    const errors: string[] = [];
    const warnings: string[] = [];
    const suggestions: string[] = [];

    const activeBlocks = blueprint.blocks.filter((b) => b.enabled);
    const categories = new Set(activeBlocks.map((b) => b.category));

    if (!categories.has('brain')) {
      errors.push('Missing Brain block: At least one LLM router/model block must be selected.');
    }

    if (!categories.has('persona')) {
      warnings.push('No Persona block attached: Agent will operate using neutral system defaults.');
      suggestions.push('Add a Persona block with clear guidelines to improve task focus.');
    }

    const hasPython = activeBlocks.some(
      (b) => b.category === 'tools' && Boolean(b.config.has_python_microtool),
    );
    if (hasPython && !categories.has('sandbox')) {
      warnings.push('Python microtools enabled without an explicit Sandbox isolation block.');
      suggestions.push('Attach a Sandbox block to constrain process timeout and file writes.');
    }

    const estimatedTokens = 250 + activeBlocks.length * 60;
    return {
      is_valid: errors.length === 0,
      errors,
      warnings,
      suggestions,
      estimated_token_cost: estimatedTokens,
    };
  }

  private fallbackDryRun(req: SandboxDryRunRequest): SandboxDryRunResult {
    const val = this.fallbackValidate(req.blueprint);
    if (!val.is_valid) {
      return {
        simulated_response: `Dry-run aborted due to validation failure: ${val.errors.join('; ')}`,
        resolved_system_prompt: '[Invalid Configuration]',
        predicted_tool_calls: [],
        latency_ms: 1,
        tokens_used: 0,
      };
    }

    const persona = req.blueprint.blocks.find(
      (b) => b.enabled && b.category === 'persona',
    );
    const basePrompt = (persona?.config.prompt_template as string) || 'Standard AI Agent Prompt';

    const predictedTools: string[] = [];
    const lower = req.prompt.toLowerCase();
    for (const b of req.blueprint.blocks) {
      if (b.enabled && b.category === 'tools') {
        const tools = (b.config.tool_names as string[]) || [];
        for (const t of tools) {
          if (['run', 'exec', 'search', 'file', 'read'].some((kw) => lower.includes(kw))) {
            if (!predictedTools.includes(t)) {
              predictedTools.push(t);
            }
          }
        }
      }
    }

    return {
      simulated_response: `Simulated offline response for: "${req.prompt}"\n- Model: ${req.blueprint.name}\n- Tools: ${predictedTools.join(', ') || 'Direct'}\n- Baseline Tokens: ${val.estimated_token_cost}`,
      resolved_system_prompt: basePrompt,
      predicted_tool_calls: predictedTools,
      latency_ms: 24,
      tokens_used: val.estimated_token_cost + 45,
    };
  }
}

export const assemblerService = new AssemblerService();
