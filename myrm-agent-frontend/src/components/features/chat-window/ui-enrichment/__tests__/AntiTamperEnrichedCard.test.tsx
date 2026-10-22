import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { describe, expect, it } from 'vitest';
import { AntiTamperEnrichedCard } from '../AntiTamperEnrichedCard';
import { EnrichedPresentationResult } from '../uiEnrichmentTypes';

describe('AntiTamperEnrichedCard', () => {
  const mockResult: EnrichedPresentationResult = {
    presentationId: 'pres-card-test-1',
    createdAt: Date.now(),
    items: [
      {
        id: 'prod-hw-1',
        officialTitle: '企业级大模型推理专机',
        officialPrice: 29999,
        officialCurrency: 'CNY',
        stockStatus: 'in_stock',
        sanitizedNote: '权威核准：售价 ¥29999，推荐高并发业务部署',
        comparisonHighlight: '综合性能第一',
        rank: 1,
        isEnriched: true,
      },
    ],
    auditLog: {
      totalRequested: 2,
      enrichedCount: 1,
      droppedUnknownIds: ['fake-device-999'],
      currencyFixedCount: 1,
      temporalFixedCount: 0,
      auditNotes: [
        '[溯源拦截] 模型推荐的 ID 「fake-device-999」在权威事实库中无有效记录，已自动移出卡片',
        '[币种对齐] ID 「prod-hw-1」模型文本币种与系统权威定价币种 (CNY) 冲突，已自动校准',
      ],
    },
  };

  it('renders card title, anti-tamper badge, official title, and locked price accurately', () => {
    render(<AntiTamperEnrichedCard result={mockResult} />);

    expect(
      screen.getByTestId('anti-tamper-card-pres-card-test-1'),
    ).toBeDefined();
    expect(screen.getByText('权威事实防篡改卡片')).toBeDefined();
    expect(
      screen.getByText('服务端事实全量 Join · 零模型伪造风险'),
    ).toBeDefined();
    expect(screen.getByText('企业级大模型推理专机')).toBeDefined();
    expect(screen.getByText('¥29999')).toBeDefined();
    expect(
      screen.getByText(/权威核准：售价 ¥29999，推荐高并发业务部署/),
    ).toBeDefined();
    expect(screen.getByText('综合性能第一')).toBeDefined();
  });

  it('toggles audit log details when audit button is clicked', () => {
    render(<AntiTamperEnrichedCard result={mockResult} />);

    const auditBtn = screen.getByText(/防篡改门禁已执行安全清洗 \(2 项记录\)/);
    expect(auditBtn).toBeDefined();

    expect(
      screen.queryByText(/模型推荐的 ID 「fake-device-999」在权威事实库中无有效记录/),
    ).toBeNull();

    // 点击展开审计明细
    fireEvent.click(auditBtn);
    expect(
      screen.getByText(/模型推荐的 ID 「fake-device-999」在权威事实库中无有效记录/),
    ).toBeDefined();
    expect(
      screen.getByText(/模型文本币种与系统权威定价币种 \(CNY\) 冲突/),
    ).toBeDefined();

    // 再次点击折叠
    fireEvent.click(auditBtn);
    expect(
      screen.queryByText(/模型推荐的 ID 「fake-device-999」在权威事实库中无有效记录/),
    ).toBeNull();
  });

  it('renders clean card without audit accordion when no issues were detected', () => {
    const cleanResult: EnrichedPresentationResult = {
      presentationId: 'clean-pres',
      createdAt: Date.now(),
      items: [
        {
          id: 'clean-1',
          officialTitle: '标准合规设备',
          officialPrice: 100,
          officialCurrency: 'USD',
          stockStatus: 'in_stock',
          sanitizedNote: '完全合规',
          rank: 1,
          isEnriched: true,
        },
      ],
      auditLog: {
        totalRequested: 1,
        enrichedCount: 1,
        droppedUnknownIds: [],
        currencyFixedCount: 0,
        temporalFixedCount: 0,
        auditNotes: [],
      },
    };

    render(<AntiTamperEnrichedCard result={cleanResult} />);

    expect(screen.getByText('标准合规设备')).toBeDefined();
    expect(screen.getByText('$100')).toBeDefined();
    expect(screen.queryByText(/防篡改门禁已执行安全清洗/)).toBeNull();
  });
});
