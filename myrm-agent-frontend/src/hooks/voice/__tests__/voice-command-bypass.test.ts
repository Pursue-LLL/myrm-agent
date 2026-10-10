import { describe, expect, it } from 'vitest';
import {
  matchVoiceCommandBypass,
  normalizeVoiceInput,
} from '@/hooks/voice/voice-command-bypass';

describe('voice-command-bypass', () => {
  describe('normalizeVoiceInput', () => {
    it('strips colloquial prefixes and trailing punctuation', () => {
      expect(normalizeVoiceInput('请帮我停止！')).toBe('停止');
      expect(normalizeVoiceInput('麻烦你先帮我暂停... ')).toBe('暂停');
      expect(normalizeVoiceInput('  赶紧取消！  ')).toBe('取消');
      expect(normalizeVoiceInput('现在继续。')).toBe('继续');
    });
  });

  describe('matchVoiceCommandBypass', () => {
    it('matches tier-0 control commands', () => {
      const stopRes = matchVoiceCommandBypass('请帮我停止');
      expect(stopRes.tier).toBe('tier0_local_bypass');
      expect(stopRes.action).toBe('stop_execution');

      const pauseRes = matchVoiceCommandBypass('先停一下');
      expect(pauseRes.tier).toBe('tier0_local_bypass');
      expect(pauseRes.action).toBe('pause_execution');

      const resumeRes = matchVoiceCommandBypass('继续');
      expect(resumeRes.tier).toBe('tier0_local_bypass');
      expect(resumeRes.action).toBe('resume_execution');

      const retryRes = matchVoiceCommandBypass('重新跑');
      expect(retryRes.tier).toBe('tier0_local_bypass');
      expect(retryRes.action).toBe('retry_execution');
    });

    it('matches tier-0 navigation and view commands', () => {
      const chatRes = matchVoiceCommandBypass('新建会话');
      expect(chatRes.tier).toBe('tier0_local_bypass');
      expect(chatRes.action).toBe('new_session');

      const clearRes = matchVoiceCommandBypass('清空对话');
      expect(clearRes.tier).toBe('tier0_local_bypass');
      expect(clearRes.action).toBe('clear_history');

      const kanbanRes = matchVoiceCommandBypass('打开看板');
      expect(kanbanRes.tier).toBe('tier0_local_bypass');
      expect(kanbanRes.action).toBe('open_taskboard');

      const settingsRes = matchVoiceCommandBypass('打开设置');
      expect(settingsRes.tier).toBe('tier0_local_bypass');
      expect(settingsRes.action).toBe('open_settings');
    });

    it('falls back to tier-1 agent LLM for complex tasks and empty inputs', () => {
      expect(matchVoiceCommandBypass('').tier).toBe('tier1_agent_llm');

      const complexRes1 = matchVoiceCommandBypass('请帮我分析一下刚才那段代码里的内存泄漏');
      expect(complexRes1.tier).toBe('tier1_agent_llm');
      expect(complexRes1.action).toBeUndefined();

      const complexRes2 = matchVoiceCommandBypass('停止所有的子任务并把结果写进 report.md');
      expect(complexRes2.tier).toBe('tier1_agent_llm');
      expect(complexRes2.action).toBeUndefined();
    });
  });
});
