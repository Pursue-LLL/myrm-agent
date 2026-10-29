import { describe, it, expect } from 'vitest';
import {
  OFFICE_MODES,
  resolveModeSecurityPolicy,
  detectWriteIntentInAskMode,
} from '../threeModeEngine';

describe('threeModeEngine 核心逻辑单测', () => {
  it('OFFICE_MODES 应具备完整的 Ask/Plan/Craft 三态定义与明确权限边界', () => {
    expect(OFFICE_MODES.ask.id).toBe('ask');
    expect(OFFICE_MODES.ask.policy.readOnly).toBe(true);
    expect(OFFICE_MODES.ask.policy.allowFileWrites).toBe(false);

    expect(OFFICE_MODES.plan.id).toBe('plan');
    expect(OFFICE_MODES.plan.policy.requirePlanApproval).toBe(true);
    expect(OFFICE_MODES.plan.policy.allowFileWrites).toBe(false);

    expect(OFFICE_MODES.craft.id).toBe('craft');
    expect(OFFICE_MODES.craft.policy.allowFileWrites).toBe(true);
    expect(OFFICE_MODES.craft.policy.allowShellExecution).toBe(true);
  });

  it('resolveModeSecurityPolicy 准确返回对应模式的安全策略', () => {
    const askPolicy = resolveModeSecurityPolicy('ask');
    expect(askPolicy.readOnly).toBe(true);

    const craftPolicy = resolveModeSecurityPolicy('craft');
    expect(craftPolicy.allowFileWrites).toBe(true);
  });

  it('detectWriteIntentInAskMode 在 Ask 模式检测到写入关键词时触发引导提示', () => {
    const result1 = detectWriteIntentInAskMode('请帮我修改文件并保存到 doc.md', 'ask');
    expect(result1.hasWriteIntent).toBe(true);
    expect(result1.suggestedMode).toBe('craft');
    expect(result1.guidanceMessage).toContain('写操作意图');
    expect(result1.matchedKeywords).toContain('保存到');

    const result2 = detectWriteIntentInAskMode('请解释一下这个合同的主要条款', 'ask');
    expect(result2.hasWriteIntent).toBe(false);
    expect(result2.matchedKeywords.length).toBe(0);
  });

  it('detectWriteIntentInAskMode 在非 Ask 模式下不阻断用户输入', () => {
    const result = detectWriteIntentInAskMode('请创建文件 output.ts', 'craft');
    expect(result.hasWriteIntent).toBe(false);
  });
});
