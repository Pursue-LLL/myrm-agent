import { describe, expect, it, vi, beforeEach } from 'vitest';

import {
  DEFAULT_LOOP_INTERVAL_MS,
  MIN_LOOP_INTERVAL_MS,
  executeLoopSlashCommand,
  formatIntervalReadable,
  parseLoopCommandInput,
  parseNaturalInterval,
} from '../loopSlashCommand';

// Mock dependencies
vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: vi.fn(),
}));

const mockCreateCronJob = vi.fn();
const mockTriggerCronJob = vi.fn();

vi.mock('@/services/cron', () => ({
  createCronJob: (...args: unknown[]) => mockCreateCronJob(...args),
  triggerCronJob: (...args: unknown[]) => mockTriggerCronJob(...args),
}));

let mockChatState = {
  chatId: 'chat_test_123',
  loading: false,
  selectedPersona: { id: 'persona_dev' },
};

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: () => mockChatState,
  },
}));

describe('parseNaturalInterval', () => {
  it('parses english units correctly', () => {
    expect(parseNaturalInterval('10m')).toBe(600_000);
    expect(parseNaturalInterval('1h')).toBe(3_600_000);
    expect(parseNaturalInterval('2d')).toBe(172_800_000);
    expect(parseNaturalInterval('30s')).toBe(MIN_LOOP_INTERVAL_MS); // enforces min 1m
    expect(parseNaturalInterval('every 20m')).toBe(1_200_000);
    expect(parseNaturalInterval('each 2 hours')).toBe(7_200_000);
  });

  it('parses chinese units and natural phrases', () => {
    expect(parseNaturalInterval('10分钟')).toBe(600_000);
    expect(parseNaturalInterval('2小时')).toBe(7_200_000);
    expect(parseNaturalInterval('半小时')).toBe(1_800_000);
    expect(parseNaturalInterval('1个半小时')).toBe(5_400_000);
    expect(parseNaturalInterval('每天')).toBe(86_400_000);
    expect(parseNaturalInterval('每隔15分钟')).toBe(900_000);
    expect(parseNaturalInterval('每2小时')).toBe(7_200_000);
  });

  it('handles fallback and invalid inputs', () => {
    expect(parseNaturalInterval('')).toBe(DEFAULT_LOOP_INTERVAL_MS);
    expect(parseNaturalInterval('invalid_str')).toBe(DEFAULT_LOOP_INTERVAL_MS);
  });
});

describe('parseLoopCommandInput', () => {
  it('parses prefix interval', () => {
    const res = parseLoopCommandInput('/loop 5m 检查构建状态');
    expect(res.intervalMs).toBe(300_000);
    expect(res.prompt).toBe('检查构建状态');
  });

  it('parses chinese prefix interval', () => {
    const res = parseLoopCommandInput('/loop 10分钟 检查PR列表');
    expect(res.intervalMs).toBe(600_000);
    expect(res.prompt).toBe('检查PR列表');
  });

  it('parses prefix phrase', () => {
    const res = parseLoopCommandInput('/loop 每隔半小时 监控服务健康');
    expect(res.intervalMs).toBe(1_800_000);
    expect(res.prompt).toBe('监控服务健康');
  });

  it('parses suffix interval', () => {
    const res = parseLoopCommandInput('/loop check deploy every 2 hours');
    expect(res.intervalMs).toBe(7_200_000);
    expect(res.prompt).toBe('check deploy');
  });

  it('parses chinese suffix interval', () => {
    const res = parseLoopCommandInput('/loop 抓取竞品数据 每隔2小时');
    expect(res.intervalMs).toBe(7_200_000);
    expect(res.prompt).toBe('抓取竞品数据');
  });

  it('parses plain suffix interval', () => {
    const res = parseLoopCommandInput('/loop 检查构建 10分钟');
    expect(res.intervalMs).toBe(600_000);
    expect(res.prompt).toBe('检查构建');
  });

  it('defaults interval when no interval prefix/suffix exists', () => {
    const res = parseLoopCommandInput('/loop 帮我盯竞品动态');
    expect(res.intervalMs).toBe(DEFAULT_LOOP_INTERVAL_MS);
    expect(res.prompt).toBe('帮我盯竞品动态');
  });

  it('handles empty input', () => {
    const res = parseLoopCommandInput('/loop');
    expect(res.intervalMs).toBe(DEFAULT_LOOP_INTERVAL_MS);
    expect(res.prompt).toBe('');
  });
});

describe('formatIntervalReadable', () => {
  it('formats seconds, minutes, hours, days', () => {
    expect(formatIntervalReadable(30_000)).toBe('30s');
    expect(formatIntervalReadable(300_000)).toBe('5m');
    expect(formatIntervalReadable(3_600_000)).toBe('1h');
    expect(formatIntervalReadable(5_400_000)).toBe('1h30m');
    expect(formatIntervalReadable(86_400_000)).toBe('1d');
  });
});

describe('executeLoopSlashCommand', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockChatState = {
      chatId: 'chat_test_123',
      loading: false,
      selectedPersona: { id: 'persona_dev' },
    };
    mockCreateCronJob.mockResolvedValue({ id: 'cron_job_999' });
    mockTriggerCronJob.mockResolvedValue({ triggered: true });
  });

  it('returns warning when streaming', async () => {
    mockChatState.loading = true;
    const res = await executeLoopSlashCommand('/loop 5m check status');
    expect(res.success).toBe(false);
    expect(mockCreateCronJob).not.toHaveBeenCalled();
  });

  it('returns info when prompt is missing', async () => {
    const res = await executeLoopSlashCommand('/loop');
    expect(res.success).toBe(false);
    expect(mockCreateCronJob).not.toHaveBeenCalled();
  });

  it('successfully creates job and triggers first-run', async () => {
    const res = await executeLoopSlashCommand('/loop 5m 检查构建');
    expect(res.success).toBe(true);
    expect(mockCreateCronJob).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Loop: 检查构建',
        job_type: 'agent',
        schedule: { kind: 'interval', interval_ms: 300_000 },
        prompt: '检查构建',
        chat_id: 'chat_test_123',
        agent_id: 'persona_dev',
        session_target: 'main',
      }),
    );
    expect(mockTriggerCronJob).toHaveBeenCalledWith('cron_job_999');
  });
});
