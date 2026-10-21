import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { PlaybookPrefillModal } from '../PlaybookPrefillModal';
import { useNonCodingPlaybookStore } from '../useNonCodingPlaybookStore';
import { PlaybookScenario } from '../nonCodingPlaybookTypes';

describe('PlaybookPrefillModal', () => {
  const sampleScenario: PlaybookScenario = {
    id: 'sc-test-invoice',
    title: '智能发票报销整理测试',
    category: 'finance',
    description: '发票整理描述',
    inputPlaceholder: '路径',
    toolsUsed: ['ocr'],
    expectedOutput: '明细表.xlsx',
    pipelineFlow: ['扫描 OCR', '生成表格'],
    parameters: [
      {
        id: 'invoice_path',
        label: '发票所在路径',
        type: 'text',
        defaultValue: './invoices',
      },
      {
        id: 'company_title',
        label: '标准报销开票抬头',
        type: 'text',
        defaultValue: '测试公司',
      },
    ],
    defaultPromptTemplate:
      '请处理 {{invoice_path}} 目录发票，抬头为 {{company_title}}。',
  };

  beforeEach(() => {
    useNonCodingPlaybookStore.getState().reset();
  });

  it('renders nothing when activeScenarioModal is null', () => {
    const { container } = render(<PlaybookPrefillModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with pipeline steps and default prompt preview', () => {
    useNonCodingPlaybookStore.getState().openScenarioModal(sampleScenario);
    render(<PlaybookPrefillModal />);

    expect(
      screen.getByTestId('playbook-prefill-modal'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('智能发票报销整理测试'),
    ).toBeInTheDocument();
    expect(screen.getByText('扫描 OCR')).toBeInTheDocument();
    expect(screen.getByText('生成表格')).toBeInTheDocument();
    expect(screen.getByDisplayValue('./invoices')).toBeInTheDocument();
    expect(screen.getByDisplayValue('测试公司')).toBeInTheDocument();
    expect(
      screen.getByText(
        '请处理 ./invoices 目录发票，抬头为 测试公司。',
      ),
    ).toBeInTheDocument();
  });

  it('updates prompt preview when user edits form field', () => {
    useNonCodingPlaybookStore.getState().openScenarioModal(sampleScenario);
    render(<PlaybookPrefillModal />);

    const pathInput = screen.getByDisplayValue('./invoices');
    act(() => {
      fireEvent.change(pathInput, {
        target: { value: '/data/2026/receipts' },
      });
    });

    expect(
      screen.getByText(
        '请处理 /data/2026/receipts 目录发票，抬头为 测试公司。',
      ),
    ).toBeInTheDocument();
  });

  it('submits prefilled prompt and triggers onPrefillSubmit callback', () => {
    const handleSubmit = vi.fn();
    useNonCodingPlaybookStore.getState().openScenarioModal(sampleScenario);
    render(<PlaybookPrefillModal onPrefillSubmit={handleSubmit} />);

    const submitBtn = screen.getByRole('button', {
      name: /装填并立即执行/,
    });
    act(() => {
      fireEvent.click(submitBtn);
    });

    expect(handleSubmit).toHaveBeenCalledTimes(1);
    expect(handleSubmit).toHaveBeenCalledWith(
      '请处理 ./invoices 目录发票，抬头为 测试公司。',
      sampleScenario,
    );
    expect(
      useNonCodingPlaybookStore.getState().activeScenarioModal,
    ).toBeNull();
  });

  it('closes modal when Escape key is pressed', () => {
    useNonCodingPlaybookStore.getState().openScenarioModal(sampleScenario);
    render(<PlaybookPrefillModal />);

    expect(
      screen.getByTestId('playbook-prefill-modal'),
    ).toBeInTheDocument();

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    expect(
      useNonCodingPlaybookStore.getState().activeScenarioModal,
    ).toBeNull();
  });
});
