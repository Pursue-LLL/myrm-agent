import { describe, expect, it, beforeAll } from 'vitest';

import {
  getClarificationNotificationTitle,
  mapTaskStepStatus,
  resolveClarificationFormFromEventData,
  resolveStreamLocale,
} from '../streamHelpers';
import { preloadNotificationCopy } from '@/lib/i18n/streamNotificationCopy';

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
