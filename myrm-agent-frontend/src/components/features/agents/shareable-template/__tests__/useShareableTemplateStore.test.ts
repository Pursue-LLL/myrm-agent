import { describe, it, expect, beforeEach } from 'vitest';
import {
  useShareableTemplateStore,
  scrubAgentSecrets,
  evaluateDependencies,
} from '../useShareableTemplateStore';
import type { BotTemplateEntity } from '../shareableTemplateTypes';

describe('useShareableTemplateStore & Utilities', () => {
  beforeEach(() => {
    useShareableTemplateStore.getState().resetState();
  });

  describe('scrubAgentSecrets', () => {
    it('correctly scrubs sensitive API keys and generates slot placeholders', () => {
      const rawAgent = {
        id: 'agent-123',
        name: 'Web Researcher',
        description: 'Auto web researcher with Perplexity and Google',
        baseModel: 'claude-3-5-sonnet',
        systemPrompt: 'You are an intelligent researcher.',
        skills: ['browser', 'search'],
        env: {
          SERPER_API_KEY: 'secret-val-123',
          NORMAL_CONFIG: 'some-endpoint',
          AUTH_TOKEN: 'token-abc',
        },
      };

      const audit = scrubAgentSecrets(rawAgent);

      expect(audit.isSafe).toBe(true);
      expect(audit.scrubbedKeysCount).toBe(2);
      expect(audit.scrubbedFieldNames).toContain('SERPER_API_KEY');
      expect(audit.scrubbedFieldNames).toContain('AUTH_TOKEN');
      expect(audit.sanitizedEntity.environmentKeySlots).toEqual([
        '${SERPER_API_KEY}',
        '${AUTH_TOKEN}',
      ]);
      expect(audit.sanitizedEntity.title).toBe('Web Researcher');
      expect(audit.sanitizedEntity.slug).toContain('web-researcher');
    });

    it('redacts hardcoded sk- and ghp_ keys inside systemPrompt', () => {
      const rawAgent = {
        id: 'agent-456',
        name: 'Prompt Leaker',
        description: 'Has hardcoded tokens',
        baseModel: 'gpt-4o',
        systemPrompt: 'Use this key: sk-abcdefghijklmnopqrstuvwxyz1234567890 to call OpenAI',
      };

      const audit = scrubAgentSecrets(rawAgent);

      expect(audit.scrubbedFieldNames).toContain('systemPrompt_hardcoded_secret');
      expect(audit.sanitizedEntity.systemPrompt).not.toContain('sk-abcdefghijklmnopqrstuvwxyz1234567890');
      expect(audit.sanitizedEntity.systemPrompt).toContain('[REDACTED_SECRET]');
    });

    it('handles clean agents with zero secrets cleanly', () => {
      const rawAgent = {
        id: 'agent-clean',
        name: 'Clean Helper',
        description: 'No secrets at all',
        baseModel: 'qwen-2.5-72b',
        systemPrompt: 'Friendly assistant.',
        env: {
          APP_NAME: 'MyRM',
        },
      };

      const audit = scrubAgentSecrets(rawAgent);

      expect(audit.scrubbedKeysCount).toBe(0);
      expect(audit.sanitizedEntity.environmentKeySlots).toHaveLength(0);
    });
  });

  describe('evaluateDependencies', () => {
    const mockTemplate: BotTemplateEntity = {
      id: 'tpl-1',
      slug: 'coder-bot',
      title: 'Coder Bot',
      description: 'Expert programmer',
      authorHandle: '@expert',
      avatarIconName: 'Code',
      baseModel: 'deepseek-coder-v2',
      systemPrompt: 'Write clean code.',
      requiredSkills: ['git-commit', 'docker-run', 'terminal'],
      environmentKeySlots: [],
      createdAt: 1000,
    };

    it('identifies when base model is locally present', () => {
      const report = evaluateDependencies(
        mockTemplate,
        ['deepseek-coder-v2', 'gpt-4o'],
        ['git-commit', 'docker-run', 'terminal']
      );

      expect(report.modelAvailable).toBe(true);
      expect(report.missingSkills).toHaveLength(0);
      expect(report.canOneClickClone).toBe(true);
    });

    it('recommends fallback model and flags missing skills when not aligned', () => {
      const report = evaluateDependencies(
        mockTemplate,
        ['qwen-2.5-coder', 'claude-3-7-sonnet'],
        ['terminal']
      );

      expect(report.modelAvailable).toBe(false);
      expect(report.recommendedFallbackModel).toBe('qwen-2.5-coder');
      expect(report.missingSkills).toEqual(['git-commit', 'docker-run']);
    });
  });

  describe('useShareableTemplateStore actions', () => {
    it('manages open/close share modal lifecycle', () => {
      const store = useShareableTemplateStore.getState();

      store.openShareModal({
        id: 'agent-99',
        name: 'Reviewer Agent',
        description: 'Reviews code',
        baseModel: 'claude-3-5-sonnet',
        systemPrompt: 'Strict reviewer',
      });

      const updated = useShareableTemplateStore.getState();
      expect(updated.isShareModalOpen).toBe(true);
      expect(updated.activeTemplate?.title).toBe('Reviewer Agent');
      expect(updated.publishedUrl).toContain('https://myrmagent.ai/t/');

      updated.closeShareModal();
      expect(useShareableTemplateStore.getState().isShareModalOpen).toBe(false);
    });

    it('executes clone and returns execution result', () => {
      const template: BotTemplateEntity = {
        id: 'tpl-test',
        slug: 'test-bot',
        title: 'Test Bot',
        description: 'Test',
        authorHandle: '@dev',
        avatarIconName: 'Bot',
        baseModel: 'gpt-4o',
        systemPrompt: 'Hi',
        requiredSkills: [],
        environmentKeySlots: [],
        createdAt: 2000,
      };

      const store = useShareableTemplateStore.getState();
      store.openCloneDeck(template, ['claude-3-5-sonnet'], []);

      expect(useShareableTemplateStore.getState().isCloneDeckOpen).toBe(true);

      const result = useShareableTemplateStore.getState().executeClone();
      expect(result.success).toBe(true);
      expect(result.agentName).toBe('Test Bot (已克隆)');
      expect(result.appliedModel).toBe('claude-3-5-sonnet');
      expect(useShareableTemplateStore.getState().isCloneDeckOpen).toBe(true);
      expect(useShareableTemplateStore.getState().lastCloneResult).toEqual(result);
    });
  });
});
