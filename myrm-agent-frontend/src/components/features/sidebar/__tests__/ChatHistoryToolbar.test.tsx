import { fireEvent, render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { ChatHistoryToolbar } from '../ChatHistoryToolbar';
import type { HistorySearch } from '../useHistorySearch';

vi.mock('@/components/features/settings/sections/integration/channels/ChannelIcon', () => ({
  default: ({ channelId, size }: { channelId: string; size: number }) => (
    <span data-testid="channel-icon" data-channel={channelId} data-size={size} />
  ),
}));

const makeSearch = (overrides: Partial<HistorySearch> = {}): HistorySearch => ({
  showSearch: false,
  localKeyword: '',
  searchInputRef: createRef<HTMLInputElement>(),
  handleSearchChange: vi.fn(),
  handleClearSearch: vi.fn(),
  handleToggleSearch: vi.fn(),
  ...overrides,
});

function renderToolbar(
  props: Partial<Parameters<typeof ChatHistoryToolbar>[0]> = {},
  searchOverrides: Partial<HistorySearch> = {},
) {
  const search = makeSearch(searchOverrides);
  const onSourceClick = vi.fn();
  const onEnterBatch = vi.fn();
  const view = render(
    <ChatHistoryToolbar
      sources={['web', 'telegram']}
      activeSource={null}
      onSourceClick={onSourceClick}
      search={search}
      appliedKeyword=""
      loading={false}
      canEnterBatch
      onEnterBatch={onEnterBatch}
      isMobile={false}
      {...props}
    />,
  );
  return { ...view, search, onSourceClick, onEnterBatch };
}

/** The `size-N` utility is N × 4px, which is how every control of the toolbar states its target. */
const targetPx = (element: HTMLElement) => {
  const match = /(?:^|\s)size-(\d+)(?:\s|$)/.exec(element.className);
  if (!match) {
    throw new Error(`no size-N class on <${element.tagName.toLowerCase()} class="${element.className}">`);
  }
  return Number(match[1]) * 4;
};

describe('ChatHistoryToolbar source chips', () => {
  it('shows chips only when there is more than one source or a filter is on', () => {
    const { rerender, onSourceClick, onEnterBatch, search } = renderToolbar({ sources: ['web'] });
    expect(screen.queryByTitle('web')).toBeNull();

    const props = { onSourceClick, onEnterBatch, search, appliedKeyword: '', loading: false, canEnterBatch: true };
    rerender(<ChatHistoryToolbar {...props} sources={['web']} activeSource="web" isMobile={false} />);
    expect(screen.getByTitle('web')).toBeInTheDocument();
  });

  it('reports which chip is pressed so a screen reader hears the filter', () => {
    renderToolbar({ activeSource: 'telegram' });

    expect(screen.getByTitle('telegram')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTitle('web')).toHaveAttribute('aria-pressed', 'false');
  });

  it('reports the clicked source', () => {
    const { onSourceClick } = renderToolbar();

    fireEvent.click(screen.getByTitle('telegram'));

    expect(onSourceClick).toHaveBeenCalledExactlyOnceWith('telegram');
  });
});

describe('ChatHistoryToolbar targets', () => {
  it('keeps every control at least 24px on a pointer device', () => {
    renderToolbar();

    expect(targetPx(screen.getByTitle('web'))).toBeGreaterThanOrEqual(24);
    expect(targetPx(screen.getByTitle('telegram'))).toBeGreaterThanOrEqual(24);
    expect(targetPx(screen.getByRole('button', { name: 'common.search' }))).toBeGreaterThanOrEqual(24);
    expect(targetPx(screen.getByRole('button', { name: 'chat.batch.enter' }))).toBeGreaterThanOrEqual(24);
  });

  it('gives a phone finger-sized targets', () => {
    renderToolbar({ isMobile: true });

    expect(targetPx(screen.getByTitle('web'))).toBeGreaterThanOrEqual(40);
    expect(targetPx(screen.getByRole('button', { name: 'common.search' }))).toBeGreaterThanOrEqual(44);
    expect(targetPx(screen.getByRole('button', { name: 'chat.batch.enter' }))).toBeGreaterThanOrEqual(44);
  });

  it('wraps many sources onto more lines and keeps the buttons on the first one', () => {
    const sources = ['web', 'telegram', 'feishu', 'wechat', 'slack', 'discord', 'dingtalk', 'qq'];
    renderToolbar({ isMobile: true, sources });

    const chipGroup = screen.getByTitle('web').closest('div');
    expect(chipGroup).toHaveClass('flex-wrap');
    expect(chipGroup?.parentElement).toHaveClass('items-start');
    expect(chipGroup).not.toContainElement(screen.getByRole('button', { name: 'common.search' }));
  });

  it('draws the chip icons larger on a phone', () => {
    const desktop = renderToolbar();
    expect(Number(screen.getAllByTestId('channel-icon')[0]?.getAttribute('data-size'))).toBe(14);
    desktop.unmount();

    renderToolbar({ isMobile: true });
    expect(Number(screen.getAllByTestId('channel-icon')[0]?.getAttribute('data-size'))).toBe(18);
  });

  it('hides the batch button unless the list allows batch selection', () => {
    const { onEnterBatch, rerender, search, onSourceClick } = renderToolbar();
    fireEvent.click(screen.getByRole('button', { name: 'chat.batch.enter' }));
    expect(onEnterBatch).toHaveBeenCalledTimes(1);

    rerender(
      <ChatHistoryToolbar
        sources={['web', 'telegram']}
        activeSource={null}
        onSourceClick={onSourceClick}
        search={search}
        appliedKeyword=""
        loading={false}
        canEnterBatch={false}
        onEnterBatch={onEnterBatch}
        isMobile={false}
      />,
    );
    expect(screen.queryByRole('button', { name: 'chat.batch.enter' })).toBeNull();
  });
});

describe('ChatHistoryToolbar search field', () => {
  const openField = (props: Parameters<typeof renderToolbar>[0] = {}, search: Partial<HistorySearch> = {}) =>
    renderToolbar(props, { showSearch: true, ...search });

  it('stays out of the way until the search button opens it', () => {
    const { search } = renderToolbar();
    expect(screen.queryByPlaceholderText('common.search')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'common.search' }));

    expect(search.handleToggleSearch).toHaveBeenCalledTimes(1);
  });

  it('writes the placeholder in the full muted text color', () => {
    openField();

    const { className } = screen.getByPlaceholderText('common.search');
    expect(className).toContain('placeholder:text-muted-foreground');
    expect(className).not.toMatch(/placeholder:text-muted-foreground\//);
  });

  it('types at 16px on a phone so the keyboard does not zoom the page, and 12px elsewhere', () => {
    const desktop = openField();
    expect(screen.getByPlaceholderText('common.search').className).toContain('text-xs');
    desktop.unmount();

    openField({ isMobile: true });
    const { className } = screen.getByPlaceholderText('common.search');
    expect(className).toContain('text-base');
    expect(className).not.toContain('text-xs');
  });

  it('offers a named clear button once there is something to clear', () => {
    const empty = openField();
    expect(screen.queryByRole('button', { name: 'chat.historySearch.clear' })).toBeNull();
    empty.unmount();

    const { search } = openField({}, { localKeyword: 'abc' });
    const clear = screen.getByRole('button', { name: 'chat.historySearch.clear' });
    expect(targetPx(clear)).toBeGreaterThanOrEqual(24);

    fireEvent.click(clear);
    expect(search.handleClearSearch).toHaveBeenCalledTimes(1);
  });

  it('gives the clear button a finger-sized target on a phone', () => {
    openField({ isMobile: true }, { localKeyword: 'abc' });

    expect(targetPx(screen.getByRole('button', { name: 'chat.historySearch.clear' }))).toBeGreaterThanOrEqual(40);
  });

  it('forwards typing and Escape to the search state', () => {
    const { search } = openField({}, { localKeyword: 'ab' });
    const input = screen.getByPlaceholderText('common.search');

    fireEvent.change(input, { target: { value: 'abc' } });
    expect(search.handleSearchChange).toHaveBeenCalledExactlyOnceWith('abc');

    fireEvent.keyDown(input, { key: 'Escape' });
    expect(search.handleClearSearch).toHaveBeenCalledTimes(1);
  });

  it('lights the search button while a keyword is applied or the field is open', () => {
    const applied = renderToolbar({ appliedKeyword: 'abc' });
    expect(screen.getByRole('button', { name: 'common.search' }).className).toContain('bg-primary/15');
    applied.unmount();

    const open = openField();
    expect(screen.getByRole('button', { name: 'common.search' }).className).toContain('bg-primary/15');
    open.unmount();

    renderToolbar();
    expect(screen.getByRole('button', { name: 'common.search' }).className).not.toContain('bg-primary/15');
  });
});
