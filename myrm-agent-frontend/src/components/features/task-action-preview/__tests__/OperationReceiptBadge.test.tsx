import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OperationReceiptBadge } from '../OperationReceiptBadge';
import type { ImmutableOperationReceipt } from '../taskActionPreviewTypes';

describe('OperationReceiptBadge', () => {
  const mockSuccessReceipt: ImmutableOperationReceipt = {
    receiptId: 'rcpt-7788',
    actionId: 'act-001',
    actionType: 'goal_lifecycle',
    operator: 'Alice (SecOps)',
    timestamp: 1757000000000,
    targetSha: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    status: 'success',
    statusCode: 200,
    summary: '已成功安全挂起长程 Goal-998，并持久化状态快照。',
    auditPayloadHash: 'sha256-payload-audit-token-998',
  };

  const mockFailedReceipt: ImmutableOperationReceipt = {
    receiptId: 'rcpt-7789',
    actionId: 'act-002',
    actionType: 'file_mutation',
    operator: 'Bob',
    timestamp: 1757000000000,
    targetSha: 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    status: 'failed',
    statusCode: 403,
    summary: '文件写入被只读沙箱策略拦截。',
    auditPayloadHash: 'sha256-payload-audit-token-403',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders collapsed receipt badge with status code and short SHA', () => {
    render(<OperationReceiptBadge receipt={mockSuccessReceipt} />);
    expect(screen.getByText(/200 SUCCESS/)).toBeDefined();
    expect(screen.getByText(/ID: rcpt-7788/)).toBeDefined();
    expect(screen.getByText('e3b0c442')).toBeDefined();
    // Detail should not be visible when collapsed
    expect(screen.queryByText(/Alice \(SecOps\)/)).toBeNull();
  });

  it('expands detail card on click and shows full audit metadata', () => {
    render(<OperationReceiptBadge receipt={mockSuccessReceipt} />);
    const toggleBtn = screen.getByRole('button', { name: /操作回执审计摘要/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText('Alice (SecOps)')).toBeDefined();
    expect(screen.getByText(mockSuccessReceipt.summary)).toBeDefined();
    expect(screen.getByText(mockSuccessReceipt.targetSha)).toBeDefined();
    expect(screen.getByText(/Audit Hash: sha256-payload-audit-token-998/)).toBeDefined();
  });

  it('copies full SHA to clipboard when copy button is clicked', () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<OperationReceiptBadge receipt={mockSuccessReceipt} defaultExpanded={true} />);
    const copyBtn = screen.getByRole('button', { name: /复制 SHA 签名/i });
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith(mockSuccessReceipt.targetSha);
    expect(copyBtn.textContent).toContain('已复制');
  });

  it('renders failed receipt badge with error styling', () => {
    render(<OperationReceiptBadge receipt={mockFailedReceipt} defaultExpanded={true} />);
    expect(screen.getByText(/403 FAILED/)).toBeDefined();
    expect(screen.getByText(mockFailedReceipt.summary)).toBeDefined();
  });
});
