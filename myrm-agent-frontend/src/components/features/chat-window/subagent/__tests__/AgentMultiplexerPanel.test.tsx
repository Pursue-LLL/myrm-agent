'use client';

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import AgentMultiplexerPanel, {
  MultiplexerSessionItem,
} from '../AgentMultiplexerPanel';

const translations: Record<string, string> = {
  sessionListTitle: '多路会话切片',
  panesCount: '切片',
  headlessBadge: '无头',
  inspectLogTitle: '实时探查日志 (Tail 50)',
  noLogs: '暂无日志输出',
  artifactsLabel: '已生成工件',
  instructPlaceholder: '输入交互式指导指令或纠偏参数...',
  sendInstruction: '注入指导',
  pendingDirectives: '条指令待处理',
  noSessions: '当前无活跃的多路复用会话',
};
const stableT = (key: string) => translations[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockSessions: MultiplexerSessionItem[] = [
  {
    sessionId: 'sess-worker-1',
    agentType: 'coder',
    taskObjective: '实现数据库连接池与自动重连',
    state: 'running',
    isHeadless: false,
    logTail: ['Initializing connection pool...', 'Connected to PostgreSQL.'],
    artifacts: ['/workspace/pool.py'],
    pendingInstructionsCount: 0,
  },
  {
    sessionId: 'sess-worker-2',
    agentType: 'researcher',
    taskObjective: '检索最新安全漏洞通告',
    state: 'blocked',
    isHeadless: true,
    logTail: ['Rate limit reached on NVD endpoint.'],
    artifacts: [],
    pendingInstructionsCount: 1,
  },
];

describe('AgentMultiplexerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders session list with status and headless badge', () => {
    render(<AgentMultiplexerPanel sessions={mockSessions} />);

    expect(screen.getByTestId('agent-multiplexer-panel')).toBeInTheDocument();
    expect(screen.getByText('多路会话切片')).toBeInTheDocument();
    expect(screen.getByText('coder')).toBeInTheDocument();
    expect(screen.getByText('researcher')).toBeInTheDocument();
    expect(screen.getByText('无头')).toBeInTheDocument();
  });

  it('renders logs and artifacts for the active session', () => {
    render(<AgentMultiplexerPanel sessions={mockSessions} />);

    // Default first session is active
    expect(screen.getByText('Initializing connection pool...')).toBeInTheDocument();
    expect(screen.getByText('/workspace/pool.py')).toBeInTheDocument();
  });

  it('switches active session when another tab is clicked', () => {
    const handleSelect = vi.fn();
    render(
      <AgentMultiplexerPanel
        sessions={mockSessions}
        onSelectSession={handleSelect}
      />
    );

    const researcherTab = screen.getByTestId('session-tab-sess-worker-2');
    fireEvent.click(researcherTab);

    expect(handleSelect).toHaveBeenCalledWith('sess-worker-2');
    expect(screen.getByText('Rate limit reached on NVD endpoint.')).toBeInTheDocument();
    expect(screen.getByText('1 条指令待处理')).toBeInTheDocument();
  });

  it('submits interactive instruction steering directive', async () => {
    const handleInstruct = vi.fn();
    render(
      <AgentMultiplexerPanel
        sessions={mockSessions}
        onInstruct={handleInstruct}
      />
    );

    const input = screen.getByTestId('instruct-input');
    const submitBtn = screen.getByTestId('instruct-submit-btn');

    fireEvent.change(input, {
      target: { value: 'Switch to secondary mirror endpoint with backoff' },
    });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(handleInstruct).toHaveBeenCalledWith(
        'sess-worker-1',
        'Switch to secondary mirror endpoint with backoff'
      );
    });
  });

  it('renders empty state when no sessions are provided', () => {
    render(<AgentMultiplexerPanel sessions={[]} />);
    expect(screen.getByText('当前无活跃的多路复用会话')).toBeInTheDocument();
  });
});
