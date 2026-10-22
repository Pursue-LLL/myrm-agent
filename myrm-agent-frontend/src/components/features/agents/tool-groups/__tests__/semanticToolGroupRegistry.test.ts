/**
 * Semantic Tool Group Registry Unit Tests
 */

import { describe, expect, it } from 'vitest';
import {
  calculateSecurityMetrics,
  compileToolExecutionPolicy,
  PRESET_CONFIGS,
  SEMANTIC_TOOL_GROUPS,
} from '../semanticToolGroupRegistry';

describe('semanticToolGroupRegistry', () => {
  it('should define exactly 6 standard semantic tool groups', () => {
    expect(SEMANTIC_TOOL_GROUPS).toHaveLength(6);
    const groupIds = SEMANTIC_TOOL_GROUPS.map((g) => g.id);
    expect(groupIds).toEqual(['runtime', 'filesystem', 'memory', 'web', 'ui', 'messaging']);
  });

  it('should verify each group contains at least 3 tools with risk metadata', () => {
    for (const group of SEMANTIC_TOOL_GROUPS) {
      expect(group.tools.length).toBeGreaterThanOrEqual(3);
      for (const tool of group.tools) {
        expect(tool.id).toBeTruthy();
        expect(tool.name).toBeTruthy();
        expect(['safe', 'moderate', 'high_risk']).toContain(tool.risk);
      }
    }
  });

  it('should compute high security score for strict_safe preset', () => {
    const metrics = calculateSecurityMetrics(PRESET_CONFIGS.strict_safe);
    expect(metrics.riskScore).toBeGreaterThanOrEqual(75);
    expect(metrics.overallRisk).toBe('safe');
  });

  it('should compile execution policy properly with denied and allowed tools', () => {
    const policy = compileToolExecutionPolicy(PRESET_CONFIGS.strict_safe);
    // strict_safe disables runtime bash and exec, so those should be denied
    expect(policy.deniedTools).toContain('bash_session');
    expect(policy.allowedTools).toContain('read_file');
    expect(policy.groupPolicies.filesystem.enabled).toBe(true);
    expect(policy.groupPolicies.runtime.enabled).toBe(false);
  });

  it('should detect elevation requirement when unrestricted security level is set', () => {
    const devPolicy = compileToolExecutionPolicy(PRESET_CONFIGS.dev_expert);
    expect(devPolicy.elevationRequired).toBe(true);
    expect(devPolicy.allowedTools).toContain('write_file');
    expect(devPolicy.allowedTools).toContain('exec_command');
  });
});
