import { describe, expect, it, beforeAll } from 'vitest';

import {
  getClarificationNotificationTitle,
  getUserFriendlyError,
  mapTaskStepStatus,
  mergeMessageSources,
  resolveClarificationFormFromEventData,
  resolveStreamLocale,
} from '../streamHelpers';
import { preloadNotificationCopy } from '@/lib/i18n/streamNotificationCopy';

describe('mergeMessageSources', () => {
  it('deduplicates by normalized final url after citation resolve', () => {
    const merged = mergeMessageSources(
      [
        {
          index: 1,
          type: 'web_search',
          url: 'https://real.example/article',
          redirect_url: 'https://redirect-a.example/r',
          title: 'A',
        },
      ],
      [
        {
          index: 2,
          type: 'web_search',
          url: 'https://real.example/article',
          redirect_url: 'https://redirect-b.example/r',
          title: 'B',
        },
      ],
    );
    expect(merged).toHaveLength(1);
    expect(merged[0]?.url).toBe('https://real.example/article');
    expect(merged[0]?.title).toBe('B');
  });
});

describe('mapTaskStepStatus', () => {
  it('maps harness checklist and planner terminal statuses', () => {
    expect(mapTaskStepStatus('success')).toBe('success');
    expect(mapTaskStepStatus('completed')).toBe('success');
    expect(mapTaskStepStatus('error')).toBe('error');
    expect(mapTaskStepStatus('failed')).toBe('error');
    expect(mapTaskStepStatus('skipped')).toBe('cancelled');
    expect(mapTaskStepStatus('cancelled')).toBe('cancelled');
    expect(mapTaskStepStatus('partial_success')).toBe('warning');
  });

  it('returns undefined for in-flight harness statuses', () => {
    expect(mapTaskStepStatus('running')).toBeUndefined();
    expect(mapTaskStepStatus('pending')).toBeUndefined();
    expect(mapTaskStepStatus('in_progress')).toBeUndefined();
    expect(mapTaskStepStatus(undefined)).toBeUndefined();
  });
});

const productionClarifyPayload = {
  type: 'ask_question',
  form: {
    title: 'Framework choice',
    questions: [
      {
        id: 'framework',
        prompt: 'Which AI framework?',
        options: [
          { id: 'langchain', label: 'LangChain' },
          { id: 'llamaindex', label: 'LlamaIndex' },
        ],
      },
    ],
  },
};

describe('resolveClarificationFormFromEventData', () => {
  it('unwraps production SSE wire payload with nested form', () => {
    const form = resolveClarificationFormFromEventData(productionClarifyPayload);
    expect(form?.title).toBe('Framework choice');
    expect(form?.questions).toHaveLength(1);
    expect(form?.questions[0]?.id).toBe('framework');
    expect(form?.questions[0]?.options?.[0]?.id).toBe('langchain');
  });

  it('returns undefined when nested form has no valid questions', () => {
    expect(
      resolveClarificationFormFromEventData({
        type: 'ask_question',
        form: { title: 'Empty', questions: [] },
      }),
    ).toBeUndefined();
  });

  it('normalizes requires_confirmation and context metadata', () => {
    const form = resolveClarificationFormFromEventData({
      type: 'ask_question',
      form: {
        title: 'Confirm delete',
        requires_confirmation: true,
        context: 'This action cannot be undone.',
        questions: [{ id: 'confirm', prompt: 'Proceed?' }],
      },
    });
    expect(form?.requiresConfirmation).toBe(true);
    expect(form?.context).toBe('This action cannot be undone.');
  });

  it('omits requiresConfirmation when field is false or absent', () => {
    const absent = resolveClarificationFormFromEventData(productionClarifyPayload);
    expect(absent?.requiresConfirmation).toBeUndefined();

    const explicitFalse = resolveClarificationFormFromEventData({
      type: 'ask_question',
      form: {
        requires_confirmation: false,
        questions: [{ id: 'q1', prompt: 'Pick one?' }],
      },
    });
    expect(explicitFalse?.requiresConfirmation).toBeUndefined();
  });
});

describe('clarification notification i18n', () => {
  beforeAll(async () => {
    await preloadNotificationCopy();
  });

  it('resolves stream locales for five supported languages', () => {
    expect(resolveStreamLocale('zh-CN')).toBe('zh');
    expect(resolveStreamLocale('ja')).toBe('ja');
    expect(resolveStreamLocale('ko-KR')).toBe('ko');
    expect(resolveStreamLocale('de-DE')).toBe('de');
    expect(resolveStreamLocale('en-US')).toBe('en');
  });

  it('returns localized clarification notification titles', () => {
    expect(getClarificationNotificationTitle('en')).toBe('Agent needs your input');
    expect(getClarificationNotificationTitle('zh')).toBe('Agent 需要您的输入');
    expect(getClarificationNotificationTitle('ja')).toContain('Agent');
    expect(getClarificationNotificationTitle('ko')).toContain('Agent');
    expect(getClarificationNotificationTitle('de')).toContain('Agent');
  });
});

describe('getUserFriendlyError', () => {
  const originalLang = document.documentElement.lang;

  afterEach(() => {
    document.documentElement.lang = originalLang;
  });

  it('maps concurrency_limit to a friendly zh message when locale is zh', async () => {
    document.documentElement.lang = 'zh-CN';
    const result = await getUserFriendlyError('concurrency_limit', 'raw internal error');
    expect(result.message).toContain('并发会话已达上限');
  });

  it('maps concurrency_limit to a friendly en message for non-zh locales', async () => {
    document.documentElement.lang = 'en-US';
    const result = await getUserFriendlyError('concurrency_limit', 'raw internal error');
    expect(result.message).toContain('Concurrency limit reached');
  });

  it('passes through raw error for unknown kinds', async () => {
    document.documentElement.lang = 'en-US';
    const result = await getUserFriendlyError('unknown', 'Some raw error text');
    expect(result.message).toBe('Some raw error text');
  });

  it('passes through raw error when errorKind is undefined', async () => {
    const result = await getUserFriendlyError(undefined, 'Plain fallback');
    expect(result.message).toBe('Plain fallback');
  });
});
