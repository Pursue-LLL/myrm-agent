import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ScaffoldingDocPreviewModal } from '../ScaffoldingDocPreviewModal';
import { useWorkspaceScaffoldingStore } from '../useWorkspaceScaffoldingStore';
import { GeneratedScaffoldDoc } from '../workspaceScaffoldingTypes';

describe('ScaffoldingDocPreviewModal', () => {
  beforeEach(() => {
    useWorkspaceScaffoldingStore.getState().reset();
  });

  const sampleDoc: GeneratedScaffoldDoc = {
    path: '/ws/AGENTS.md',
    title: 'AGENTS.md（智能体行为规约与红线手册）',
    purpose: '明确禁止大模型擅自改动 01 原件，定义各分区协作边界',
    draftContent: '# AGENTS.md 守则\n\n1. 严禁修改 01_raw_materials 原件。',
  };

  it('renders nothing when isPreviewModalOpen is false', () => {
    const { container } = render(<ScaffoldingDocPreviewModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders doc modal and content when open', () => {
    useWorkspaceScaffoldingStore.getState().openDocPreview(sampleDoc);

    render(<ScaffoldingDocPreviewModal />);

    expect(
      screen.getByTestId('scaffolding-doc-preview-modal'),
    ).toBeDefined();
    expect(
      screen.getByText('AGENTS.md（智能体行为规约与红线手册）'),
    ).toBeDefined();
    expect(
      screen.getByText('明确禁止大模型擅自改动 01 原件，定义各分区协作边界'),
    ).toBeDefined();
    expect(screen.getByText('/ws/AGENTS.md')).toBeDefined();
    expect(
      screen.getByText(/严禁修改 01_raw_materials 原件/),
    ).toBeDefined();
  });

  it('supports copying draft content to clipboard', () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockImplementation(() => Promise.resolve()),
      },
    });

    useWorkspaceScaffoldingStore.getState().openDocPreview(sampleDoc);
    render(<ScaffoldingDocPreviewModal />);

    const copyBtn = screen.getByText('复制草稿');
    fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      sampleDoc.draftContent,
    );
  });

  it('closes modal when close button is clicked', () => {
    useWorkspaceScaffoldingStore.getState().openDocPreview(sampleDoc);
    render(<ScaffoldingDocPreviewModal />);

    const closeBtn = screen.getByLabelText('关闭预览');
    fireEvent.click(closeBtn);

    expect(
      useWorkspaceScaffoldingStore.getState().isPreviewModalOpen,
    ).toBe(false);
  });

  it('closes modal when Escape key is pressed', () => {
    useWorkspaceScaffoldingStore.getState().openDocPreview(sampleDoc);
    render(<ScaffoldingDocPreviewModal />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(
      useWorkspaceScaffoldingStore.getState().isPreviewModalOpen,
    ).toBe(false);
  });
});
