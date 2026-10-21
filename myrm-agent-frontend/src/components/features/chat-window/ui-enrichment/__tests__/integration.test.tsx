import { render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import { AntiTamperEnrichedCard } from '../AntiTamperEnrichedCard';
import {
  AuthoritativeFactRecord,
  ModelJudgmentInput,
} from '../uiEnrichmentTypes';
import { useUiEnrichmentStore } from '../useUiEnrichmentStore';

describe('UI Enrichment & Anti-Tamper End-to-End Integration', () => {
  beforeEach(() => {
    useUiEnrichmentStore.getState().reset();
  });

  const authoritativeFacts: AuthoritativeFactRecord[] = [
    {
      id: 'cluster-gpu-8x',
      officialTitle: '8卡 H100 训练集群',
      officialPrice: 1200000,
      officialCurrency: 'CNY',
      stockStatus: 'in_stock',
      verifiedWeekday: '周四',
    },
    {
      id: 'cloud-server-standard',
      officialTitle: '通用云算力实例',
      officialPrice: 499,
      officialCurrency: 'CNY',
      stockStatus: 'in_stock',
      verifiedWeekday: '周一',
    },
    {
      id: 'global-cdn-license',
      officialTitle: '全球边缘分发授权',
      officialPrice: 50,
      officialCurrency: 'USD',
      stockStatus: 'in_stock',
    },
  ];

  it('runs complete flow: fact seeding -> model judgment processing -> safe anti-tamper rendering', () => {
    // 1. 种子化权威事实库
    useUiEnrichmentStore.getState().seedAuthoritativeFacts(authoritativeFacts);

    // 2. 模拟大模型输出的含幻觉主观判定
    const modelJudgments: ModelJudgmentInput[] = [
      {
        id: 'cluster-gpu-8x',
        userNote: '只要 $1200000 美元即可拥有，本周五生效',
        comparisonHighlight: '适合千亿模型全量微调',
      },
      {
        id: 'fake-super-gpu-999',
        userNote: '只要 9 块钱的神奇显卡',
      },
      {
        id: 'cloud-server-standard',
        userNote: '高性价比日常开发首选',
      },
      {
        id: 'global-cdn-license',
        userNote: '只需 ¥50 元极速分发',
      },
    ];

    // 3. 执行防篡改全量 Join 与跨模态门禁
    const result = useUiEnrichmentStore
      .getState()
      .processModelJudgments(modelJudgments, 'e2e-pres-001');

    // 4. 验证事实 Join 与丢弃
    expect(result.items).toHaveLength(3); // 4 个请求中，1 个虚假 ID 被丢弃
    expect(result.auditLog.droppedUnknownIds).toEqual(['fake-super-gpu-999']);

    const first = result.items[0];
    expect(first).toBeDefined();
    expect(first?.officialTitle).toBe('8卡 H100 训练集群');
    expect(first?.officialPrice).toBe(1200000);
    expect(first?.officialCurrency).toBe('CNY');
    // 验证币种纠正与星期纠正
    expect(first?.sanitizedNote).toContain('¥1200000');
    expect(first?.sanitizedNote).toContain('周四生效');

    // 5. 挂载到 React 界面渲染
    render(<AntiTamperEnrichedCard result={result} />);

    expect(screen.getByText('8卡 H100 训练集群')).toBeDefined();
    expect(screen.getByText('¥1200000')).toBeDefined();
    expect(screen.getByText('通用云算力实例')).toBeDefined();
    expect(screen.getByText('全球边缘分发授权')).toBeDefined();
    expect(screen.getByText('$50')).toBeDefined();

    // 验证虚假设备绝不出现在界面上
    expect(screen.queryByText('fake-super-gpu-999')).toBeNull();
    expect(screen.queryByText('只要 9 块钱的神奇显卡')).toBeNull();
  });
});
