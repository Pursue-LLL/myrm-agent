import { describe, it, expect } from 'vitest';
import { detectAgentConfigChanges, areSkillConfigsEqual, type OriginalAgentSnapshot } from '../configChanges';
import type { BuiltinToolId } from '@/store/chat/types';

const DEFAULT_BUILTIN_TOOLS: BuiltinToolId[] = ['bash', 'computer'];

const makeSnapshot = (overrides?: Partial<OriginalAgentSnapshot>): OriginalAgentSnapshot => ({
  agentId: 'agent-1',
  selectedSkillIds: ['skill-a'],
  skillConfigs: { 'skill-a': { is_core: true, instance_name: null } },
  selectedMcpNames: ['mcp-x'],
  systemPrompt: 'hello',
  autoRestoreDomains: ['example.com'],
  enabledBuiltinTools: [...DEFAULT_BUILTIN_TOOLS],
  memoryDecayProfile: 'normal',
  modelSelection: { providerId: 'openai', model: 'gpt-4o' },
  fallbackModelSelection: { providerId: 'anthropic', model: 'claude-3.5-sonnet' },
  safetyFallbackModelSelection: null,
  ...overrides,
});

const makeCurrent = (overrides?: Record<string, unknown>) => ({
  agentId: 'agent-1',
  selectedSkillIds: ['skill-a'],
  skillConfigs: { 'skill-a': { is_core: true, instance_name: null } },
  selectedMcpNames: ['mcp-x'],
  systemPrompt: 'hello',
  autoRestoreDomains: ['example.com'],
  memoryDecayProfile: 'normal' as const,
  modelSelection: { providerId: 'openai', model: 'gpt-4o' },
  fallbackModelSelection: { providerId: 'anthropic', model: 'claude-3.5-sonnet' },
  safetyFallbackModelSelection: null,
  ...overrides,
});

describe('detectAgentConfigChanges', () => {
  // ========== 快速退出条件 ==========

  it('returns false when current has no agentId', () => {
    expect(detectAgentConfigChanges(makeSnapshot(), makeCurrent({ agentId: undefined }), DEFAULT_BUILTIN_TOOLS)).toBe(
      false,
    );
  });

  it('returns false when original is null', () => {
    expect(detectAgentConfigChanges(null, makeCurrent(), DEFAULT_BUILTIN_TOOLS)).toBe(false);
  });

  it('returns false when agentId mismatch', () => {
    expect(detectAgentConfigChanges(makeSnapshot(), makeCurrent({ agentId: 'agent-2' }), DEFAULT_BUILTIN_TOOLS)).toBe(
      false,
    );
  });

  // ========== 无变更 ==========

  it('returns false when configs are identical', () => {
    expect(detectAgentConfigChanges(makeSnapshot(), makeCurrent(), DEFAULT_BUILTIN_TOOLS)).toBe(false);
  });

  it('returns false when both model selections are null', () => {
    const original = makeSnapshot({ modelSelection: null, fallbackModelSelection: null });
    const current = makeCurrent({ modelSelection: null, fallbackModelSelection: null });
    expect(detectAgentConfigChanges(original, current, DEFAULT_BUILTIN_TOOLS)).toBe(false);
  });

  it('returns false when both model selections are undefined', () => {
    const original = makeSnapshot({ modelSelection: undefined, fallbackModelSelection: undefined });
    const current = makeCurrent({ modelSelection: undefined, fallbackModelSelection: undefined });
    expect(detectAgentConfigChanges(original, current, DEFAULT_BUILTIN_TOOLS)).toBe(false);
  });

  // ========== 模型选择变更 ==========

  it('detects primary model provider change', () => {
    const current = makeCurrent({
      modelSelection: { providerId: 'anthropic', model: 'gpt-4o' },
    });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects primary model name change', () => {
    const current = makeCurrent({
      modelSelection: { providerId: 'openai', model: 'gpt-4o-mini' },
    });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects primary model set to null', () => {
    const current = makeCurrent({ modelSelection: null });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects primary model set from null', () => {
    const original = makeSnapshot({ modelSelection: null });
    const current = makeCurrent({
      modelSelection: { providerId: 'openai', model: 'gpt-4o' },
    });
    expect(detectAgentConfigChanges(original, current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  // ========== Fallback 模型变更 ==========

  it('detects fallback model change', () => {
    const current = makeCurrent({
      fallbackModelSelection: { providerId: 'anthropic', model: 'claude-3-opus' },
    });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects fallback model cleared', () => {
    const current = makeCurrent({ fallbackModelSelection: null });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  // ========== Safety fallback 模型变更 ==========

  it('detects safety fallback model set', () => {
    const current = makeCurrent({
      safetyFallbackModelSelection: { providerId: 'google', model: 'gemini-pro' },
    });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('no change when safety fallback both null', () => {
    expect(detectAgentConfigChanges(makeSnapshot(), makeCurrent(), DEFAULT_BUILTIN_TOOLS)).toBe(false);
  });

  // ========== 非模型字段变更 ==========

  it('detects skill change', () => {
    const current = makeCurrent({ selectedSkillIds: ['skill-a', 'skill-b'] });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects skill instance binding change', () => {
    const current = makeCurrent({
      skillConfigs: { 'skill-a': { is_core: true, instance_name: 'work' } },
    });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects skill core flag change', () => {
    const current = makeCurrent({
      skillConfigs: { 'skill-a': { is_core: false, instance_name: null } },
    });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects MCP change', () => {
    const current = makeCurrent({ selectedMcpNames: ['mcp-y'] });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects system prompt change', () => {
    const current = makeCurrent({ systemPrompt: 'world' });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects autoRestoreDomains change', () => {
    const current = makeCurrent({ autoRestoreDomains: ['other.com'] });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  it('detects builtin tools change', () => {
    expect(detectAgentConfigChanges(makeSnapshot(), makeCurrent(), ['bash'] as BuiltinToolId[])).toBe(true);
  });

  it('detects memoryDecayProfile change', () => {
    const current = makeCurrent({ memoryDecayProfile: 'fast' });
    expect(detectAgentConfigChanges(makeSnapshot(), current, DEFAULT_BUILTIN_TOOLS)).toBe(true);
  });

  // ========== 边界情况 ==========

  it('treats undefined memoryDecayProfile as normal', () => {
    const original = makeSnapshot({ memoryDecayProfile: undefined });
    const current = makeCurrent({ memoryDecayProfile: undefined });
    expect(detectAgentConfigChanges(original, current, DEFAULT_BUILTIN_TOOLS)).toBe(false);
  });

  it('empty skills arrays are equal', () => {
    const original = makeSnapshot({ selectedSkillIds: [] });
    const current = makeCurrent({ selectedSkillIds: [] });
    expect(detectAgentConfigChanges(original, current, DEFAULT_BUILTIN_TOOLS)).toBe(false);
  });

  it('skill order does not matter', () => {
    const original = makeSnapshot({ selectedSkillIds: ['a', 'b'] });
    const current = makeCurrent({ selectedSkillIds: ['b', 'a'] });
    expect(detectAgentConfigChanges(original, current, DEFAULT_BUILTIN_TOOLS)).toBe(false);
  });
});

describe('areSkillConfigsEqual', () => {
  it('treats null instance_name same as missing field', () => {
    expect(
      areSkillConfigsEqual(
        { 'skill-a': { is_core: true, instance_name: null } },
        { 'skill-a': { is_core: true } },
      ),
    ).toBe(true);
  });

  it('detects instance_name change', () => {
    expect(
      areSkillConfigsEqual(
        { 'skill-a': { is_core: true, instance_name: null } },
        { 'skill-a': { is_core: true, instance_name: 'work' } },
      ),
    ).toBe(false);
  });

  it('detects is_core change', () => {
    expect(
      areSkillConfigsEqual(
        { 'skill-a': { is_core: true, instance_name: null } },
        { 'skill-a': { is_core: false, instance_name: null } },
      ),
    ).toBe(false);
  });

  it('ignores key order', () => {
    expect(
      areSkillConfigsEqual(
        { a: { is_core: true, instance_name: null }, b: { is_core: false, instance_name: 'x' } },
        { b: { is_core: false, instance_name: 'x' }, a: { is_core: true, instance_name: null } },
      ),
    ).toBe(true);
  });
});
