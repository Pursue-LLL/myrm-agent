import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { PrivacyRuleTester } from '../PrivacyRuleTester';
import useConfigStore from '@/store/useConfigStore';

const { mockFetchWithTimeout } = vi.hoisted(() => ({ mockFetchWithTimeout: vi.fn() }));

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: mockFetchWithTimeout,
}));

const SENTENCE = '帮我总结凤凰计划Q3预算超支原因';

function answer(preview: { level: string; action: string | null; model_sees: string | null }) {
  mockFetchWithTimeout.mockResolvedValue({ ok: true, json: async () => preview });
}

function typeSentence(text = SENTENCE) {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: text } });
}

describe('PrivacyRuleTester', () => {
  beforeEach(() => {
    mockFetchWithTimeout.mockReset();
    useConfigStore.setState({
      privacyS2Action: 'warn',
      privacyS3Action: 'redact',
      privacyCustomKeywordsS2: [],
      privacyCustomKeywordsS3: ['凤凰计划'],
      privacyCustomPatternsS2: [],
      privacyCustomPatternsS3: [],
      privacyDeepScan: false,
    });
  });

  it('asks nothing while the box is empty', async () => {
    render(<PrivacyRuleTester />);

    typeSentence('   ');
    await new Promise((resolve) => setTimeout(resolve, 600));

    expect(mockFetchWithTimeout).not.toHaveBeenCalled();
  });

  it('sends the rules of the form and shows what the model would receive', async () => {
    answer({ level: 's3', action: 'redact', model_sees: '帮我总结[REDACTED] [PII:custom]Q3预算超支原因' });
    render(<PrivacyRuleTester />);

    typeSentence();

    expect(
      await screen.findByText('帮我总结[REDACTED] [PII:custom]Q3预算超支原因', {}, { timeout: 3000 }),
    ).toBeTruthy();
    expect(screen.getByText('tester.levelS3')).toBeTruthy();
    expect(screen.getByText('tester.action:{"action":"actionRedact"}')).toBeTruthy();
    const [endpoint, init] = mockFetchWithTimeout.mock.calls[0];
    expect(endpoint).toBe('/config/privacy-preview');
    expect(JSON.parse(init.body)).toEqual({
      text: SENTENCE,
      privacy_s2_action: 'warn',
      privacy_s3_action: 'redact',
      privacy_custom_keywords_s2: [],
      privacy_custom_keywords_s3: ['凤凰计划'],
      privacy_custom_patterns_s2: [],
      privacy_custom_patterns_s3: [],
    });
  });

  it('says so when the rules would stop the message', async () => {
    answer({ level: 's3', action: 'block', model_sees: null });
    render(<PrivacyRuleTester />);

    typeSentence();

    expect(await screen.findByText('tester.blocked', {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.queryByText('tester.modelSees')).toBeNull();
  });

  it('notes that a warn-only setting sends the original', async () => {
    answer({ level: 's2', action: 'warn', model_sees: SENTENCE });
    render(<PrivacyRuleTester />);

    typeSentence();

    expect(await screen.findByText('tester.unchanged', {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.getByText('tester.levelS2')).toBeTruthy();
  });

  it('reports a clean sentence without a badge', async () => {
    answer({ level: 's1', action: null, model_sees: '今天天气不错' });
    render(<PrivacyRuleTester />);

    typeSentence('今天天气不错');

    expect(await screen.findByText('tester.levelNone', {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.queryByText('tester.levelS2')).toBeNull();
  });

  it('tells the user it could not try, without technical detail', async () => {
    mockFetchWithTimeout.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    render(<PrivacyRuleTester />);

    typeSentence();

    expect(await screen.findByText('tester.failed', {}, { timeout: 3000 })).toBeTruthy();
  });

  it('asks again when a rule changes', async () => {
    answer({ level: 's3', action: 'redact', model_sees: 'masked' });
    render(<PrivacyRuleTester />);
    typeSentence();
    await waitFor(() => expect(mockFetchWithTimeout).toHaveBeenCalledTimes(1), { timeout: 3000 });

    useConfigStore.setState({ privacyCustomKeywordsS3: ['凤凰计划', '李总'] });

    await waitFor(() => expect(mockFetchWithTimeout).toHaveBeenCalledTimes(2), { timeout: 3000 });
    expect(JSON.parse(mockFetchWithTimeout.mock.calls[1][1].body).privacy_custom_keywords_s3).toEqual([
      '凤凰计划',
      '李总',
    ]);
  });

  it('warns that deep scan is not part of the try-out', () => {
    useConfigStore.setState({ privacyDeepScan: true });
    render(<PrivacyRuleTester />);

    expect(screen.getByText('tester.deepScanNote')).toBeTruthy();
  });
});
