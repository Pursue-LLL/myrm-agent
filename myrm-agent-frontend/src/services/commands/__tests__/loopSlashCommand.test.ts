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

const mockStartSessionLoop = vi.fn();
const mockStopSessionLoop = vi.fn();
const mockGetSessionLoopStatus = vi.fn();

vi.mock('@/services/sessionLoop', () => ({
  startSessionLoop: (...args: unknown[]) => mockStartSessionLoop(...args),
  stopSessionLoop: (...args: unknown[]) => mockStopSessionLoop(...args),
  getSessionLoopStatus: (...args: unknown[]) => mockGetSessionLoopStatus(...args),
}));

let mockChatState = {
  chatId: 'chat_test_123',
  loading: false,
  actionMode: 'agent' as const,
  agentConfig: { agentId: 'persona_dev' },
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

  it('handles pure interval input without prompt by returning empty prompt', () => {
    const res1 = parseLoopCommandInput('/loop 5m');
    expect(res1.intervalMs).toBe(300_000);
    expect(res1.prompt).toBe('');

    const res2 = parseLoopCommandInput('/loop every 2h');
    expect(res2.intervalMs).toBe(7_200_000);
    expect(res2.prompt).toBe('');

    const res3 = parseLoopCommandInput('/loop 半小时');
    expect(res3.intervalMs).toBe(1_800_000);
    expect(res3.prompt).toBe('');

    const res4 = parseLoopCommandInput('/loop 每天');
    expect(res4.intervalMs).toBe(86_400_000);
    expect(res4.prompt).toBe('');

    const res5 = parseLoopCommandInput('/loop 15');
    expect(res5.intervalMs).toBe(900_000);
    expect(res5.prompt).toBe('');
  });

  it('supports aliases /repeat and /cron', () => {
    const resRepeat = parseLoopCommandInput('/repeat 10m check deploy');
    expect(resRepeat.intervalMs).toBe(600_000);
    expect(resRepeat.prompt).toBe('check deploy');

    const resCron = parseLoopCommandInput('/cron 30m monitor logs');
    expect(resCron.intervalMs).toBe(1_800_000);
    expect(resCron.prompt).toBe('monitor logs');

    const resRepeatEmpty = parseLoopCommandInput('/repeat 5m');
    expect(resRepeatEmpty.intervalMs).toBe(300_000);
    expect(resRepeatEmpty.prompt).toBe('');
  });

  it('cleans enclosing quotes from prompt', () => {
    const resDouble = parseLoopCommandInput('/loop 5m "检查 PR 状态"');
    expect(resDouble.intervalMs).toBe(300_000);
    expect(resDouble.prompt).toBe('检查 PR 状态');

    const resSingle = parseLoopCommandInput("/loop 1h 'monitor service'");
    expect(resSingle.intervalMs).toBe(3_600_000);
    expect(resSingle.prompt).toBe('monitor service');

    const resSuffix = parseLoopCommandInput('/loop "检查部署" every 10m');
    expect(resSuffix.intervalMs).toBe(600_000);
    expect(resSuffix.prompt).toBe('检查部署');
  });

  it('handles multiline prompt with special characters', () => {
    const multiline = `/loop 15m 检查流水线状态:\n1. build-linux\n2. test-darwin\n3. deploy-prod`;
    const res = parseLoopCommandInput(multiline);
    expect(res.intervalMs).toBe(900_000);
    expect(res.prompt).toContain('1. build-linux');
    expect(res.prompt).toContain('3. deploy-prod');
  });

  it('handles upper/mixed case command and units', () => {
    const res = parseLoopCommandInput('/LOOP 2H Check Metrics');
    expect(res.intervalMs).toBe(7_200_000);
    expect(res.prompt).toBe('Check Metrics');
  });

  it('extracts --times and --until flags correctly', () => {
    const res1 = parseLoopCommandInput('/loop 5m check deploy --times 10');
    expect(res1.intervalMs).toBe(300_000);
    expect(res1.prompt).toBe('check deploy');
    expect(res1.times).toBe(10);
    expect(res1.until).toBeUndefined();

    const res2 = parseLoopCommandInput('/loop 10m run test --until completed');
    expect(res2.intervalMs).toBe(600_000);
    expect(res2.prompt).toBe('run test');
    expect(res2.times).toBeUndefined();
    expect(res2.until).toBe('completed');

    const res3 = parseLoopCommandInput('/loop 5m check status --times 5 --until build is green');
    expect(res3.intervalMs).toBe(300_000);
    expect(res3.prompt).toBe('check status');
    expect(res3.times).toBe(5);
    expect(res3.until).toBe('build is green');
  });

  it('extracts flags and returns empty prompt when prompt body is missing', () => {
    const res1 = parseLoopCommandInput('/loop 5m --times 10');
    expect(res1.intervalMs).toBe(300_000);
    expect(res1.prompt).toBe('');
    expect(res1.times).toBe(10);

    const res2 = parseLoopCommandInput('/loop --until done');
    expect(res2.intervalMs).toBe(DEFAULT_LOOP_INTERVAL_MS);
    expect(res2.prompt).toBe('');
    expect(res2.until).toBe('done');
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
      actionMode: 'agent' as const,
      agentConfig: { agentId: 'persona_dev' },
    };
    mockStartSessionLoop.mockResolvedValue({
      is_active: true,
      status: 'active',
      current_delay_human: '5m',
    });
    mockStopSessionLoop.mockResolvedValue({
      is_active: false,
      status: 'stopped',
    });
    mockGetSessionLoopStatus.mockResolvedValue({
      is_active: false,
      status: 'none',
      current_delay_human: '',
      ticks_fired: 0,
    });
  });

  it('returns warning when streaming', async () => {
    mockChatState.loading = true;
    const res = await executeLoopSlashCommand('/loop 5m check status');
    expect(res.success).toBe(false);
    expect(mockStartSessionLoop).not.toHaveBeenCalled();
  });

  it('returns error when chatId is missing', async () => {
    mockChatState.chatId = '';
    const res = await executeLoopSlashCommand('/loop 5m check status');
    expect(res.success).toBe(false);
    expect(res.error).toBe('No active chat session');
    expect(mockStartSessionLoop).not.toHaveBeenCalled();
  });

  it('returns info when prompt is missing', async () => {
    const res = await executeLoopSlashCommand('/loop');
    expect(res.success).toBe(false);
    expect(mockStartSessionLoop).not.toHaveBeenCalled();
  });

  it('returns info and blocks job creation when only interval is provided without prompt', async () => {
    const res = await executeLoopSlashCommand('/loop 5m');
    expect(res.success).toBe(false);
    expect(res.error).toBe('Missing loop prompt');
    expect(mockStartSessionLoop).not.toHaveBeenCalled();
  });

  it('blocks job creation when flags are provided but task prompt is empty', async () => {
    const res1 = await executeLoopSlashCommand('/loop 5m --times 10');
    expect(res1.success).toBe(false);
    expect(res1.error).toBe('Missing loop prompt');

    const res2 = await executeLoopSlashCommand('/loop --until done');
    expect(res2.success).toBe(false);
    expect(res2.error).toBe('Missing loop prompt');

    expect(mockStartSessionLoop).not.toHaveBeenCalled();
  });

  it('reports active status when /loop status is called and loop is active', async () => {
    mockGetSessionLoopStatus.mockResolvedValue({
      is_active: true,
      status: 'active',
      current_delay_human: '5m',
      ticks_fired: 3,
    });
    const res = await executeLoopSlashCommand('/loop status');
    expect(res.success).toBe(true);
    expect(mockGetSessionLoopStatus).toHaveBeenCalledWith('chat_test_123');
    expect(mockStartSessionLoop).not.toHaveBeenCalled();
  });

  it('reports inactive status when /loop status is called and no loop is running', async () => {
    mockGetSessionLoopStatus.mockResolvedValue({
      is_active: false,
      status: 'none',
      current_delay_human: '',
      ticks_fired: 0,
    });
    const res = await executeLoopSlashCommand('/loop status');
    expect(res.success).toBe(true);
    expect(mockGetSessionLoopStatus).toHaveBeenCalledWith('chat_test_123');
    expect(mockStartSessionLoop).not.toHaveBeenCalled();
  });

  it('handles status query exception gracefully', async () => {
    mockGetSessionLoopStatus.mockRejectedValue(new Error('Query error'));
    const res = await executeLoopSlashCommand('/loop status');
    expect(res.success).toBe(false);
    expect(res.error).toBe('Failed to query loop status');
  });

  it('successfully stops active loop when /loop stop is called and dispatches event', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const res = await executeLoopSlashCommand('/loop stop');
    expect(res.success).toBe(true);
    expect(mockStopSessionLoop).toHaveBeenCalledWith('chat_test_123');
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'session-loop-changed' }));
    expect(mockStartSessionLoop).not.toHaveBeenCalled();
  });

  it('handles stop failure gracefully', async () => {
    mockStopSessionLoop.mockRejectedValue(new Error('Stop failed'));
    const res = await executeLoopSlashCommand('/loop stop');
    expect(res.success).toBe(false);
    expect(res.error).toBe('Failed to stop loop');
  });

  it('successfully starts session loop with prompt and dispatches event', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const res = await executeLoopSlashCommand('/loop 5m 检查构建');
    expect(res.success).toBe(true);
    expect(mockStartSessionLoop).toHaveBeenCalledWith('chat_test_123', '/loop 5m 检查构建');
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'session-loop-changed' }));
  });

  it('handles start API failure gracefully', async () => {
    mockStartSessionLoop.mockRejectedValue(new Error('Network error'));
    const res = await executeLoopSlashCommand('/loop 10m 检查网络');
    expect(res.success).toBe(false);
    expect(res.error).toBe('Loop command exception');
  });
});
