import React from 'react';
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandMatrixModal } from '../CommandMatrixModal';
import { useCommandMatrixStore } from '../useCommandMatrixStore';
import type { CommandMatrixEntry } from '../commandMatrixTypes';

describe('CommandMatrixModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useCommandMatrixStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockCommands: CommandMatrixEntry[] = [
    {
      command: '/btw',
      category: 'concurrency_collaboration',
      title_zh: '旁路插话提问',
      title_en: 'Barge-in Query',
      description_zh: '临时提问不打断主任务',
      description_en: 'Ask a side question without stopping main run',
      shortcut: 'Cmd+B',
      prompt_template: '/btw ',
      tags: ['concurrency', 'steer'],
      requires_running_task: true,
    },
    {
      command: '/pykernel',
      category: 'data_science',
      title_zh: '会话持久 Python 内核',
      title_en: 'Persistent Python REPL',
      description_zh: '保活 DataFrame 与变量内存',
      description_en: 'Keep Python kernel alive across turns',
      shortcut: 'Alt+P',
      prompt_template: '/pykernel start',
      tags: ['python', 'jupyter'],
      requires_running_task: false,
    },
    {
      command: '/sop',
      category: 'delivery_workflow',
      title_zh: '固化 SOP 技能',
      title_en: 'Solidify SOP Skill',
      description_zh: '提炼为可复用技能',
      description_en: 'Distill traces into reusable SOP skill',
      shortcut: null,
      prompt_template: '/sop create',
      tags: ['sop', 'skill'],
      requires_running_task: false,
    },
  ];

  it('renders nothing when isModalOpen is false', () => {
    const { container } = render(<CommandMatrixModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog, header, search input and commands list when open', () => {
    useCommandMatrixStore.setState({
      isModalOpen: true,
      commands: mockCommands,
    });

    render(<CommandMatrixModal />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/searchPlaceholder|搜索/i)).toBeInTheDocument();
    expect(screen.getByText('/btw')).toBeInTheDocument();
    expect(screen.getByText('/pykernel')).toBeInTheDocument();
    expect(screen.getByText('/sop')).toBeInTheDocument();
  });

  it('filters commands via search input', () => {
    useCommandMatrixStore.setState({
      isModalOpen: true,
      commands: mockCommands,
    });

    render(<CommandMatrixModal />);

    const searchInput = screen.getByPlaceholderText(/searchPlaceholder|搜索/i);
    fireEvent.change(searchInput, { target: { value: 'python' } });

    expect(screen.getByText('/pykernel')).toBeInTheDocument();
    expect(screen.queryByText('/btw')).toBeNull();
    expect(screen.queryByText('/sop')).toBeNull();
  });

  it('filters commands by category tab selection', () => {
    useCommandMatrixStore.setState({
      isModalOpen: true,
      commands: mockCommands,
    });

    render(<CommandMatrixModal />);

    // Click data_science category tab
    const dataTab = screen.getByRole('button', { name: /数据与科学|data_science/i });
    fireEvent.click(dataTab);

    expect(screen.getByText('/pykernel')).toBeInTheDocument();
    expect(screen.queryByText('/btw')).toBeNull();
  });

  it('triggers onSelectCommand and closes modal on command card click', () => {
    const onSelectSpy = vi.fn();
    useCommandMatrixStore.setState({
      isModalOpen: true,
      commands: mockCommands,
    });

    render(<CommandMatrixModal onSelectCommand={onSelectSpy} />);

    const btwCard = screen.getByText('/btw').closest('button[class*="group"]');
    expect(btwCard).not.toBeNull();
    if (btwCard) {
      fireEvent.click(btwCard);
    }

    expect(onSelectSpy).toHaveBeenCalledWith(mockCommands[0]);
    expect(useCommandMatrixStore.getState().isModalOpen).toBe(false);
    expect(useCommandMatrixStore.getState().masteredCommands).toContain('/btw');
  });

  it('closes modal when clicking close button', () => {
    useCommandMatrixStore.setState({
      isModalOpen: true,
      commands: mockCommands,
    });

    render(<CommandMatrixModal />);

    const closeBtn = screen.getByLabelText(/close|关闭/i);
    fireEvent.click(closeBtn);

    expect(useCommandMatrixStore.getState().isModalOpen).toBe(false);
  });
});
