import React from 'react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { UiVariantCompareViewer } from '../UiVariantCompareViewer';
import { useUiAlignmentStore } from '../useUiAlignmentStore';
import type { UiVariantItem, VisualContractItem } from '../uiAlignmentTypes';

describe('UiVariantCompareViewer', () => {
  const mockVariants: UiVariantItem[] = [
    {
      variant_id: 'var_01',
      title: 'Modern Bento Grid',
      style_theme: 'modern_bento',
      html_content: '<div class="bento">Bento Content</div>',
      css_tokens: { '--bg-card': '#18181b', '--accent': '#6366f1' },
      description: 'High information density',
      created_at_ms: 1000,
    },
    {
      variant_id: 'var_02',
      title: 'Minimal Dark Layout',
      style_theme: 'minimal_dark',
      html_content: '<div class="dark">Minimal Content</div>',
      css_tokens: { '--bg-card': '#09090b' },
      description: 'Clean typographic layout',
      created_at_ms: 2000,
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    useUiAlignmentStore.getState().reset();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ code: 0, data: mockVariants }),
    } as unknown as Response);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <UiVariantCompareViewer chatId="test_chat" isOpen={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog and variant items when isOpen is true', () => {
    useUiAlignmentStore.setState({
      variants: mockVariants,
      selectedVariantId: 'var_01',
      isLoading: false,
    });

    render(<UiVariantCompareViewer chatId="test_chat" isOpen={true} />);

    // Dialog heading
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();

    // Verify variants displayed in sidebar
    expect(screen.getAllByText('Modern Bento Grid').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Minimal Dark Layout')).toBeInTheDocument();

    // Tokens displayed
    expect(screen.getByText('--bg-card: #18181b')).toBeInTheDocument();
    expect(screen.getByText('--accent: #6366f1')).toBeInTheDocument();
  });

  it('switches active variant on variant item click', () => {
    useUiAlignmentStore.setState({
      variants: mockVariants,
      selectedVariantId: 'var_01',
    });

    render(<UiVariantCompareViewer chatId="test_chat" isOpen={true} />);

    const minimalBtn = screen.getByRole('button', { name: /Minimal Dark Layout/i });
    fireEvent.click(minimalBtn);

    expect(useUiAlignmentStore.getState().selectedVariantId).toBe('var_02');
  });

  it('toggles canvas annotate mode button', () => {
    useUiAlignmentStore.setState({
      variants: mockVariants,
      selectedVariantId: 'var_01',
      isAnnotating: false,
    });

    render(<UiVariantCompareViewer chatId="test_chat" isOpen={true} />);

    const annotateToggleBtn = screen.getByRole('button', { name: /annotateMode|画布批注/i });
    fireEvent.click(annotateToggleBtn);

    expect(useUiAlignmentStore.getState().isAnnotating).toBe(true);
  });

  it('calls finalizeContract when clicking finalize button', async () => {
    const finalizeSpy = vi.fn().mockResolvedValue(null);
    useUiAlignmentStore.setState({
      variants: mockVariants,
      selectedVariantId: 'var_01',
      finalizeContract: finalizeSpy,
      isLoading: false,
      fetchVariants: vi.fn().mockResolvedValue(undefined),
      fetchContract: vi.fn().mockResolvedValue(undefined),
    });

    render(<UiVariantCompareViewer chatId="test_chat" isOpen={true} />);

    const finalizeBtn = screen.getByRole('button', { name: /finalizeContract|固化视觉契约/i });
    fireEvent.click(finalizeBtn);

    expect(finalizeSpy).toHaveBeenCalledWith('test_chat', 'var_01');
  });

  it('renders finalized contract badge and prompt details', () => {
    const mockContract: VisualContractItem = {
      contract_id: 'vc_test_999',
      session_id: 'test_chat',
      approved_variant_id: 'var_01',
      style_theme: 'modern_bento',
      dom_outline: '<div>Bento</div>',
      design_tokens: { '--accent': '#6366f1' },
      annotations_count: 2,
      enforcement_prompt: '### [VISUAL DESIGN CONTRACT ENFORCEMENT]\nAdhere strictly to modern_bento',
      finalized_at_ms: 3000,
    };

    useUiAlignmentStore.setState({
      variants: mockVariants,
      selectedVariantId: 'var_01',
      activeContract: mockContract,
    });

    render(<UiVariantCompareViewer chatId="test_chat" isOpen={true} />);

    // Check badge renders
    const badge = screen.getAllByText(/contractFinalizedBadge|契约已固化/i);
    expect(badge.length).toBeGreaterThan(0);

    // Expand accordion
    const accordionBtn = screen.getByRole('button', { name: /contractFinalizedBadge.*vc_test_999|契约已固化.*vc_test_999/i });
    fireEvent.click(accordionBtn);

    expect(screen.getByText(/Adhere strictly to modern_bento/i)).toBeInTheDocument();
  });

  it('triggers onClose callback when clicking close button', () => {
    const onCloseSpy = vi.fn();
    useUiAlignmentStore.setState({
      variants: mockVariants,
      selectedVariantId: 'var_01',
    });

    render(<UiVariantCompareViewer chatId="test_chat" isOpen={true} onClose={onCloseSpy} />);

    const closeBtn = screen.getByRole('button', { name: /close|关闭/i });
    fireEvent.click(closeBtn);

    expect(onCloseSpy).toHaveBeenCalledTimes(1);
  });
});
