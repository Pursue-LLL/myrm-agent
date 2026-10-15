import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { SearchAuditEvidenceBadge } from '../SearchAuditEvidenceBadge';
import { SearchAuditDrawer } from '../SearchAuditDrawer';
import { useSearchAuditStore } from '../useSearchAuditStore';
import { SearchAuditSession, AuditCitationItem, SubQueryTrace } from '../searchAuditTypes';
import { calculateSourceQualityMatrix } from '../searchAuditEngine';

// 模拟包含模型回答卡片与审计抽屉的完整业务容器
const MockResearchReportContainer: React.FC = () => {
  const traces: SubQueryTrace[] = [
    {
      subQueryId: 'sq-e2e-1',
      queryText: 'NeurIPS 2026 reasoning models verification',
      category: 'academic',
      latencyMs: 380,
      payloadBytes: 24576,
      isFullText: true,
      hasAiRewrite: false,
      timestamp: Date.now(),
    },
    {
      subQueryId: 'sq-e2e-2',
      queryText: 'OpenAI formal verification framework code',
      category: 'code',
      latencyMs: 290,
      payloadBytes: 32768,
      isFullText: true,
      hasAiRewrite: false,
      timestamp: Date.now(),
    },
  ];

  const citations: AuditCitationItem[] = [
    {
      id: 'cite-arxiv-reasoning',
      url: 'https://arxiv.org/abs/2602.12345',
      domain: 'arxiv.org',
      title: 'Formal Verification of Latent Reasoning Steps in LLMs',
      rawSnippet: 'We establish provable bounds for chain-of-thought verification...',
      fullTextSnippet: 'Theorem 1 (Convergence): Under bounded context entropy, verification latency satisfies O(log N)...',
      subQueryId: 'sq-e2e-1',
      qualityMatrix: calculateSourceQualityMatrix('https://arxiv.org/abs/2602.12345', true, false),
    },
    {
      id: 'cite-github-framework',
      url: 'https://github.com/openai/formal-verification',
      domain: 'github.com',
      title: 'Formal Verification Framework for Autonomous Agents',
      rawSnippet: 'Official repository containing test harnesses and benchmark suites...',
      fullTextSnippet: 'export const verifyChain = async (steps: ReasoningStep[]): Promise<ProofResult> => { ... };',
      subQueryId: 'sq-e2e-2',
      qualityMatrix: calculateSourceQualityMatrix('https://github.com/openai/formal-verification', true, false),
    },
  ];

  const session: SearchAuditSession = {
    auditSessionId: 'audit-e2e-suite',
    parentMessageId: 'msg-e2e-root',
    totalLatencyMs: 670,
    totalPayloadBytes: 57344,
    averageQualityScore: 96,
    traces,
    citations,
    createdAt: Date.now(),
  };

  return (
    <div>
      <article data-testid="research-report-card">
        <h1>严肃学术研究报告: 大模型多步推理的形式化验证</h1>
        <p>根据权威顶会论文与开源标准规范，形式化验证可显著降低长长程规划中的随机漂移。</p>

        {/* 证据链胶囊徽标 */}
        <SearchAuditEvidenceBadge session={session} />
      </article>

      {/* 右侧审计抽屉 */}
      <SearchAuditDrawer />
    </div>
  );
};

describe('SearchAudit Integration Suite', () => {
  beforeEach(() => {
    useSearchAuditStore.getState().clearSession();
  });

  it('orchestrates end-to-end evidence inspection flow across waterfall, matrix, and clean text compare', () => {
    render(<MockResearchReportContainer />);

    expect(screen.getByTestId('research-report-card')).toBeInTheDocument();

    // 1. 点击报告下方的证据链徽标
    const badge = screen.getByTestId('search-audit-evidence-badge-compact');
    fireEvent.click(badge);

    // 2. 抽屉优雅展开，展示全透明链路指标
    const drawer = screen.getByTestId('search-audit-drawer');
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByText('全透明检索链路审计')).toBeInTheDocument();
    expect(within(drawer).getByText('96 分权威源')).toBeInTheDocument();
    expect(within(drawer).getByText('670 ms')).toBeInTheDocument();
    expect(within(drawer).getByText('56.0 KB')).toBeInTheDocument();
    expect(within(drawer).getByText('2 次 API 调用')).toBeInTheDocument();

    // 3. 瀑布流中展示每一次子查询的细节
    expect(within(drawer).getByText('NeurIPS 2026 reasoning models verification')).toBeInTheDocument();
    expect(within(drawer).getByText('OpenAI formal verification framework code')).toBeInTheDocument();

    // 4. 切换到 100 分量化质量矩阵 Tab
    const matrixTab = within(drawer).getByRole('button', { name: /100分质量矩阵/i });
    fireEvent.click(matrixTab);

    expect(
      within(drawer).getByText('Formal Verification of Latent Reasoning Steps in LLMs')
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText('Formal Verification Framework for Autonomous Agents')
    ).toBeInTheDocument();
    expect(within(drawer).getByText(/CCF\/SCI 权威学术源 98分/)).toBeInTheDocument();

    // 5. 切换到可信证据反查 Tab 并查看净菜全文
    const compareTab = within(drawer).getByRole('button', { name: /可信证据反查/i });
    fireEvent.click(compareTab);

    expect(
      within(drawer).getByText('We establish provable bounds for chain-of-thought verification...')
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText(/Theorem 1 \(Convergence\): Under bounded context entropy/)
    ).toBeInTheDocument();

    // 6. 关闭抽屉，页面恢复常态
    const closeBtn = within(drawer).getByRole('button', { name: '关闭检索审计抽屉' });
    fireEvent.click(closeBtn);
    expect(useSearchAuditStore.getState().isDrawerOpen).toBe(false);
  });
});
