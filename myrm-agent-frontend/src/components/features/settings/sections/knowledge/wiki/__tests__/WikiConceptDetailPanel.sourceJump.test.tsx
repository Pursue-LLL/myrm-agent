import { act, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, ...rest }: { children: React.ReactNode }) => <button {...rest}>{children}</button>,
}));

vi.mock('@/components/primitives/badge', () => ({
  Badge: ({ children, ...rest }: { children: React.ReactNode }) => <span {...rest}>{children}</span>,
}));

vi.mock('@/components/primitives/card', async () => {
  const React = await import('react');
  return {
    Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    CardContent: React.forwardRef<HTMLDivElement, { children: React.ReactNode }>(({ children }, ref) => (
      <div ref={ref}>{children}</div>
    )),
    CardHeader: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
  };
});

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconBook: () => <span data-testid="icon-book" />,
  IconEdit: () => <span data-testid="icon-edit" />,
  IconLoader: () => <span data-testid="icon-loader" />,
  IconSave: () => <span data-testid="icon-save" />,
  IconX: () => <span data-testid="icon-x" />,
}));

vi.mock('@/components/features/message-box/MarkdownContent', () => ({
  default: () => (
    <div data-testid="markdown-content">
      <h2 data-testid="heading-fuzzy">1. 架构简介与核心概念</h2>
      <h2 data-testid="heading-exact">简介</h2>
    </div>
  ),
}));

vi.mock('../WikiConceptLinksPanel', () => ({
  WikiConceptLinksPanel: ({ onSelectConcept }: { onSelectConcept?: (name: string, heading?: string) => void }) => (
    <div id="wiki-concept-links">
      <button data-testid="mock-jump-btn" onClick={() => onSelectConcept?.('Alpha', '简介')}>
        Jump to Intro
      </button>
      <button data-testid="mock-jump-fuzzy" onClick={() => onSelectConcept?.('Alpha', '核心概念')}>
        Jump Fuzzy
      </button>
      <button data-testid="mock-jump-404" onClick={() => onSelectConcept?.('Alpha', '完全不存在的章节')}>
        Jump 404
      </button>
    </div>
  ),
}));

vi.mock('@/lib/wiki/claimStatusDisplay', () => ({
  claimStatusClass: () => 'status-class',
  claimStatusLabel: (_status: string, labels: Record<string, string>) => labels.supported ?? 'supported',
  formatClaimConfidence: () => '85%',
  shouldShowClaimConfidence: () => false,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: Array<string | false | null | undefined>) => args.filter(Boolean).join(' '),
}));

import { WikiConceptDetailPanel } from '../WikiConceptDetailPanel';
import type { Concept } from '@/services/wikiService';

const baseProps = {
  selectedConcept: null,
  isEditing: false,
  editTab: 'truth' as const,
  editContent: '',
  editCompiledTruth: '',
  editTimelineDisplay: '',
  editTimelineAppend: '',
  editTags: '',
  editAliases: '',
  isSaving: false,
  onEdit: () => {},
  onCancelEdit: () => {},
  onSave: () => {},
  onEditTabChange: () => {},
  onEditContentChange: () => {},
  onEditCompiledTruthChange: () => {},
  onEditTimelineAppendChange: () => {},
  onEditTagsChange: () => {},
  onEditAliasesChange: () => {},
};

describe('WikiConceptDetailPanel source provenance jump', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('links to message-level deep jump when source_message is present', () => {
    const concept: Concept = {
      name: 'Alpha',
      content: '# Alpha',
      provenance: 'chat_compound',
      source_chat: 'chat-123',
      source_message: 'msg-456',
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);
    const link = screen.getByText('sourceChat') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/chat-123?highlight=msg-456');
  });

  it('falls back to chat-level link when source_message is absent', () => {
    const concept: Concept = {
      name: 'Alpha',
      content: '# Alpha',
      source_chat: 'chat-123',
      source_message: null,
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);
    const link = screen.getByText('sourceChat') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/chat-123');
  });

  it('renders no provenance link when source_chat is absent', () => {
    const concept: Concept = {
      name: 'Alpha',
      content: '# Alpha',
      source_chat: null,
      source_message: null,
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);
    expect(screen.queryByText('sourceChat')).toBeNull();
  });

  it('prioritizes exact heading match over preceding fuzzy substring heading', () => {
    const scrollMock = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: scrollMock,
    });

    const concept: Concept = {
      name: 'Alpha',
      content: '## 1. 架构简介与核心概念\n## 简介',
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);

    const jumpBtn = screen.getByTestId('mock-jump-btn');
    act(() => {
      jumpBtn.click();
    });

    expect(scrollMock).toHaveBeenCalledTimes(1);
    const exactHeading = screen.getByTestId('heading-exact');
    const fuzzyHeading = screen.getByTestId('heading-fuzzy');

    // 精确匹配的标题必须获得高亮类
    expect(exactHeading.classList.contains('bg-primary/10')).toBe(true);
    // 前序模糊子串标题绝对不能被错误高亮
    expect(fuzzyHeading.classList.contains('bg-primary/10')).toBe(false);
  });

  it('falls back to fuzzy substring match when exact match is absent', () => {
    const scrollMock = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: scrollMock,
    });

    const concept: Concept = {
      name: 'Alpha',
      content: '## 1. 架构简介与核心概念\n## 简介',
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);

    const jumpBtn = screen.getByTestId('mock-jump-fuzzy');
    act(() => {
      jumpBtn.click();
    });

    expect(scrollMock).toHaveBeenCalledTimes(1);
    const fuzzyHeading = screen.getByTestId('heading-fuzzy');
    const exactHeading = screen.getByTestId('heading-exact');

    // 模糊包含目标（核心概念）命中 fuzzyHeading 并获得高亮
    expect(fuzzyHeading.classList.contains('bg-primary/10')).toBe(true);
    // 无关标题不受影响
    expect(exactHeading.classList.contains('bg-primary/10')).toBe(false);
  });

  it('gracefully ignores non-existent heading without throwing errors', () => {
    const scrollMock = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: scrollMock,
    });

    const concept: Concept = {
      name: 'Alpha',
      content: '## 1. 架构简介与核心概念\n## 简介',
    };
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);

    const jumpBtn = screen.getByTestId('mock-jump-404');
    expect(() => {
      act(() => {
        jumpBtn.click();
      });
    }).not.toThrow();

    // 完全不存在的小节不触发滚动，也不附加任何高亮
    expect(scrollMock).not.toHaveBeenCalled();
    const fuzzyHeading = screen.getByTestId('heading-fuzzy');
    const exactHeading = screen.getByTestId('heading-exact');
    expect(fuzzyHeading.classList.contains('bg-primary/10')).toBe(false);
    expect(exactHeading.classList.contains('bg-primary/10')).toBe(false);
  });
});

describe('WikiConceptDetailPanel links shortcut', () => {
  const concept: Concept = { name: 'Alpha', content: '# Alpha' };

  it('is labelled with translated copy and never hidden at any breakpoint', () => {
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);

    const shortcut = screen.getByRole('button', { name: 'links.title' });
    expect(shortcut.getAttribute('aria-label')).toBe('links.title');
    expect(shortcut.getAttribute('title')).toBe('links.title');
    // 窄屏下文字可以收起成纯图标，但按钮本身不能在任何断点被隐藏
    expect(shortcut.classList.contains('hidden')).toBe(false);
    expect(shortcut.textContent).not.toMatch(/[\u4e00-\u9fff]/);
  });

  it('scrolls the links panel into view when pressed', () => {
    const scrolledIds: string[] = [];
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value(this: HTMLElement) {
        scrolledIds.push(this.id);
      },
    });
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);

    act(() => {
      screen.getByRole('button', { name: 'links.title' }).click();
    });

    expect(scrolledIds).toEqual(['wiki-concept-links']);
  });
});

describe('WikiConceptDetailPanel header layout', () => {
  // 头部嵌在宽度不定的详情栏里（手机、平板、窄窗口）：放不下时整块换行，词条名独占一行，
  // 不能被来源徽标、来源链接和操作按钮挤到 0 宽。jsdom 不计算样式，这里只钉住换行所依赖的类名。
  const concept: Concept = {
    name: 'Alpha',
    content: '# Alpha',
    provenance: 'chat-compound',
    source_chat: 'chat-123',
  };

  it('lets the header and the title block wrap instead of squeezing the concept name', () => {
    render(<WikiConceptDetailPanel {...baseProps} selectedConcept={concept} />);

    const header = screen.getByTestId('wiki-concept-edit-btn').closest('[class~="@container"]') as HTMLElement;
    const [titleBlock, actions] = Array.from(header.children) as HTMLElement[];
    const name = within(titleBlock).getByText('Alpha');

    expect(header.classList.contains('flex-wrap')).toBe(true);
    expect(titleBlock.classList.contains('flex-wrap')).toBe(true);
    expect(titleBlock.classList.contains('truncate')).toBe(false);
    expect(name.classList.contains('max-w-full')).toBe(true);
    expect(actions.classList.contains('ml-auto')).toBe(true);
  });
});
