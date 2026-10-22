import React from 'react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DelightTemplateGalleryModal } from '../DelightTemplateGalleryModal';
import { useDelightShowcaseStore } from '../useDelightShowcaseStore';
import type { DelightTemplateItem } from '../delightTypes';

describe('DelightTemplateGalleryModal', () => {
  const mockTemplates: DelightTemplateItem[] = [
    {
      template_id: 'tmpl_bday',
      title: 'Birthday Fireworks Code Hero',
      category: 'celebration',
      description: 'Matrix rain and fireworks animation',
      prompt_seed: 'Create birthday fireworks HTML',
      html_source: '<html><body>Birthday HTML</body></html>',
      tags: ['birthday', 'fireworks'],
      icon_name: 'cake',
      is_featured: true,
      created_at_ms: 1000,
    },
    {
      template_id: 'tmpl_wheel',
      title: 'Lucky Wheel Dinner Decision',
      category: 'utility_tools',
      description: 'Wheel of dinner fortune',
      prompt_seed: 'Create lucky wheel HTML',
      html_source: '<html><body>Lucky Wheel HTML</body></html>',
      tags: ['wheel', 'decision'],
      icon_name: 'disc',
      is_featured: true,
      created_at_ms: 2000,
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    useDelightShowcaseStore.getState().reset();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ code: 0, data: mockTemplates }),
    } as unknown as Response);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isGalleryOpen is false', () => {
    useDelightShowcaseStore.setState({ isGalleryOpen: false });
    const { container } = render(<DelightTemplateGalleryModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal dialog and templates when isGalleryOpen is true', () => {
    useDelightShowcaseStore.setState({
      isGalleryOpen: true,
      templates: mockTemplates,
    });

    render(<DelightTemplateGalleryModal />);

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();

    expect(screen.getByText('Birthday Fireworks Code Hero')).toBeInTheDocument();
    expect(screen.getByText('Lucky Wheel Dinner Decision')).toBeInTheDocument();
  });

  it('filters templates when searching by keyword', () => {
    useDelightShowcaseStore.setState({
      isGalleryOpen: true,
      templates: mockTemplates,
    });

    render(<DelightTemplateGalleryModal />);

    const searchInput = screen.getByPlaceholderText(/searchPlaceholder|搜索/i);
    fireEvent.change(searchInput, { target: { value: 'Fireworks' } });

    expect(screen.getByText('Birthday Fireworks Code Hero')).toBeInTheDocument();
    expect(screen.queryByText('Lucky Wheel Dinner Decision')).not.toBeInTheDocument();
  });

  it('filters templates when switching category tab', () => {
    useDelightShowcaseStore.setState({
      isGalleryOpen: true,
      templates: mockTemplates,
    });

    render(<DelightTemplateGalleryModal />);

    // Switch to celebration tab
    const celebrationTab = screen.getByRole('button', { name: /celebration|节日庆典/i });
    fireEvent.click(celebrationTab);

    expect(screen.getByText('Birthday Fireworks Code Hero')).toBeInTheDocument();
    expect(screen.queryByText('Lucky Wheel Dinner Decision')).not.toBeInTheDocument();
  });

  it('triggers preview demo and opens sandbox showcase with html', () => {
    useDelightShowcaseStore.setState({
      isGalleryOpen: true,
      templates: mockTemplates,
    });

    render(<DelightTemplateGalleryModal />);

    const previewButtons = screen.getAllByRole('button', { name: /previewDemo|即席预览/i });
    fireEvent.click(previewButtons[0]);

    const state = useDelightShowcaseStore.getState();
    expect(state.isShowcaseOpen).toBe(true);
    expect(state.activeSandboxTitle).toBe('Birthday Fireworks Code Hero');
    expect(state.activeSandboxHtml).toBe('<html><body>Birthday HTML</body></html>');
  });

  it('triggers onApplyPrompt callback and closes modal on use template click', () => {
    const applySpy = vi.fn();
    useDelightShowcaseStore.setState({
      isGalleryOpen: true,
      templates: mockTemplates,
    });

    render(<DelightTemplateGalleryModal onApplyPrompt={applySpy} />);

    const useButtons = screen.getAllByRole('button', { name: /useTemplate|立即制作/i });
    fireEvent.click(useButtons[0]);

    expect(applySpy).toHaveBeenCalledWith('Create birthday fireworks HTML');
    expect(useDelightShowcaseStore.getState().isGalleryOpen).toBe(false);
  });

  it('closes modal when clicking close button', () => {
    useDelightShowcaseStore.setState({
      isGalleryOpen: true,
      templates: mockTemplates,
    });

    render(<DelightTemplateGalleryModal />);

    const closeBtn = screen.getByRole('button', { name: /close|关闭/i });
    fireEvent.click(closeBtn);

    expect(useDelightShowcaseStore.getState().isGalleryOpen).toBe(false);
  });
});
