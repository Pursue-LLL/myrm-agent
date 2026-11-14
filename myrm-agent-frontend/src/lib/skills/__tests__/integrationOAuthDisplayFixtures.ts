import type { Skill } from '@/store/skill/types';

/** A skill as the skills API sends it; override only what a test is about. */
export function buildSkill(overrides: Partial<Skill>): Skill {
  return {
    id: 'custom-skill',
    name: 'Custom Skill',
    description: 'test',
    type: 'prebuilt',
    storage_path: '/skills/custom',
    version: '1.0.0',
    category: 'office',
    icon_url: null,
    tags: [],
    requires: { bins: [], env: [], config: [] },
    // The skills API always sends both lists, empty when the skill declares nothing.
    required_oauth_issuers: [],
    required_mcp_server_ids: [],
    available: true,
    unavailable_reason: null,
    trust: 'installed',
    author: null,
    homepage: null,
    always: false,
    model_invocable: true,
    user_invocable: true,
    primary_env: null,
    security: null,
    user_trusted: false,
    evolution_locked: false,
    has_upstream_update: false,
    verification_steps: [],
    eval_cases: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}
