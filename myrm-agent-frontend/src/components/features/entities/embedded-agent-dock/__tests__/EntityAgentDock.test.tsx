import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EntityAgentDock } from '../EntityAgentDock';
import { useEntityEmbeddedAgentStore } from '../useEntityEmbeddedAgentStore';
import type { BusinessEntitySnapshot } from '../entityEmbeddedAgentTypes';

describe('EntityAgentDock Component', () => {
  beforeEach(() => {
    useEntityEmbeddedAgentStore.getState().resetState();
  });

  const mockDeal: BusinessEntitySnapshot = {
    id: 'ent-deal-888',
    type: 'deal',
    title: 'Acme 全年云原生集群采购合同',
    subtitle: '合同金额: $350,000 USD',
    metadata: {
      stage: '商务条款仲裁中',
      signDeadline: '2026-11-30',
    },
  };

  it('renders nothing when dock is closed', () => {
    const { container } = render(<EntityAgentDock />);
    expect(container.firstChild).toBeNull();
  });

  it('renders entity title, signed token badge and step dossier ledger when opened', () => {
    useEntityEmbeddedAgentStore.getState().openEntityDock(mockDeal);
    render(<EntityAgentDock />);

    expect(screen.getByText('Acme 全年云原生集群采购合同')).toBeInTheDocument();
    expect(screen.getByText('DEAL')).toBeInTheDocument();
    expect(screen.getByText(/免粘贴验签通过/)).toBeInTheDocument();

    // 验证推演步态透明账本
    expect(screen.getByText(/推演步态与丢弃线索透明账本/)).toBeInTheDocument();
    expect(screen.getByText('检索内部知识库与往来往历史记录')).toBeInTheDocument();
    expect(screen.getByText('已丢弃线索')).toBeInTheDocument();
    expect(screen.getByText(/排除理由:/)).toBeInTheDocument();
    expect(screen.getByText('需要人类就地仲裁')).toBeInTheDocument();
  });

  it('handles in-place disambiguation arbitration clicks', () => {
    useEntityEmbeddedAgentStore.getState().openEntityDock(mockDeal);
    render(<EntityAgentDock />);

    const vpOption = screen.getByRole('button', { name: /张伟 \(VP of Engineering\)/ });
    expect(vpOption).toBeInTheDocument();

    fireEvent.click(vpOption);

    // 确认仲裁后标题变更，且提示在会话流中呈现
    expect(screen.getByText(/已就地裁决锁定对接人：张伟 \(VP of Engineering\)/)).toBeInTheDocument();
    expect(screen.getByText(/已锁定对接人【张伟 \(VP of Engineering\)】/)).toBeInTheDocument();
  });

  it('submits user inquiry and updates chat message flow', () => {
    useEntityEmbeddedAgentStore.getState().openEntityDock(mockDeal);
    render(<EntityAgentDock />);

    const input = screen.getByPlaceholderText(/向专属智能体询问关于【Acme 全年云原生集群采购合同】的任何细节.../);
    const sendBtn = screen.getByRole('button', { name: /发送/ });

    fireEvent.change(input, { target: { value: '合同的 SLA 违约赔偿上限是多少？' } });
    fireEvent.click(sendBtn);

    expect(screen.getByText('合同的 SLA 违约赔偿上限是多少？')).toBeInTheDocument();
    expect(screen.getByText(/已基于当前实体「Acme 全年云原生集群采购合同」的专属上下文完成深度推演/)).toBeInTheDocument();
  });
});
