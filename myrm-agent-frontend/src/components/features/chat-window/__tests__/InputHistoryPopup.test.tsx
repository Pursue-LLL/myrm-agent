/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';

import type { InputHistoryPopupState } from '@/hooks/message-input/useInputHistory';

import InputHistoryPopup from '../InputHistoryPopup';

const intl = vi.hoisted(() => ({ locale: 'en' as 'en' | 'zh' }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

const NOW = new Date('2026-03-15T12:00:00Z').getTime();
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const entry = (text: string, ageMs = 0) => ({ text, createdAt: NOW - ageMs });

const handlers = () => ({ onSelect: vi.fn(), onHover: vi.fn(), onClose: vi.fn() });

function popupState(entries: InputHistoryPopupState['entries'], activeIndex = 0, open = true): InputHistoryPopupState {
  return { open, entries, activeIndex };
}

const options = () => screen.getAllByRole('option');
const tooltipOf = (index: number) => options()[index].getAttribute('title');

let scrollIntoView: MockInstance<Element['scrollIntoView']>;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  intl.locale = 'en';
  scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.useRealTimers();
  scrollIntoView.mockRestore();
});

describe('InputHistoryPopup listing', () => {
  it('lists the entries as options of a listbox named after the history', () => {
    render(<InputHistoryPopup popup={popupState([entry('first'), entry('second')])} {...handlers()} />);

    expect(screen.getByRole('listbox', { name: 'Input history' })).toBeInTheDocument();
    expect(options().map((option) => option.textContent)).toEqual(['first', 'second']);
  });

  it('shows multi-line prompts on one trimmed line and keeps the full text in the tooltip', () => {
    render(<InputHistoryPopup popup={popupState([entry('  fix\n\n the   build  ', 5 * MINUTE)])} {...handlers()} />);

    expect(options()[0]).toHaveTextContent(/^fix the build$/);
    expect(tooltipOf(0)).toBe('fix the build\n5 minutes ago');
  });

  it.each([
    ['closed', popupState([entry('a')], 0, false)],
    ['empty', popupState([])],
  ])('renders nothing while the popup is %s', (_name, popup) => {
    const { container } = render(<InputHistoryPopup popup={popup} {...handlers()} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('marks only the active entry as selected', () => {
    render(<InputHistoryPopup popup={popupState([entry('a'), entry('b'), entry('c')], 1)} {...handlers()} />);

    expect(options().map((option) => option.getAttribute('aria-selected'))).toEqual(['false', 'true', 'false']);
  });

  it('lists entries that were saved at the same instant without key clashes', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(<InputHistoryPopup popup={popupState([entry('a'), entry('b')])} {...handlers()} />);

    expect(options()).toHaveLength(2);
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});

describe('InputHistoryPopup tooltip time', () => {
  it.each([
    ['30 seconds', 30_000, 'this minute'],
    ['a minute', MINUTE, '1 minute ago'],
    ['59 minutes', 59 * MINUTE, '59 minutes ago'],
    ['an hour', HOUR, '1 hour ago'],
    ['23 hours', 23 * HOUR, '23 hours ago'],
    ['a day', DAY, 'yesterday'],
    ['6 days', 6 * DAY, '6 days ago'],
  ])('reads %s back as "%s"', (_name, ageMs, expected) => {
    render(<InputHistoryPopup popup={popupState([entry('x', ageMs)])} {...handlers()} />);

    expect(tooltipOf(0)).toBe(`x\n${expected}`);
  });

  it('gives the date from a week back on', () => {
    const timestamp = NOW - 7 * DAY;
    render(<InputHistoryPopup popup={popupState([entry('x', 7 * DAY)])} {...handlers()} />);

    expect(tooltipOf(0)).toBe(`x\n${new Date(timestamp).toLocaleDateString('en')}`);
  });

  it('words the time in the app language, not the browser language', () => {
    intl.locale = 'zh';
    render(<InputHistoryPopup popup={popupState([entry('x', 5 * MINUTE), entry('y', 7 * DAY)])} {...handlers()} />);

    expect(tooltipOf(0)).toBe('x\n5分钟前');
    expect(tooltipOf(1)).toBe(`y\n${new Date(NOW - 7 * DAY).toLocaleDateString('zh')}`);
  });
});

describe('InputHistoryPopup interaction', () => {
  it('reports the entry the pointer moves over', () => {
    const h = handlers();
    render(<InputHistoryPopup popup={popupState([entry('a'), entry('b')])} {...h} />);

    fireEvent.mouseEnter(options()[1]);

    expect(h.onHover).toHaveBeenCalledExactlyOnceWith(1);
  });

  it('selects the pressed entry without taking the focus from the input', () => {
    const h = handlers();
    render(<InputHistoryPopup popup={popupState([entry('a'), entry('b')])} {...h} />);

    const notPrevented = fireEvent.mouseDown(options()[1]);

    expect(h.onSelect).toHaveBeenCalledExactlyOnceWith(1);
    expect(notPrevented).toBe(false);
  });

  it('closes on a press outside and stays open on a press inside', () => {
    const h = handlers();
    render(<InputHistoryPopup popup={popupState([entry('a')])} {...h} />);

    fireEvent.mouseDown(options()[0]);
    expect(h.onClose).not.toHaveBeenCalled();

    fireEvent.mouseDown(document.body);
    expect(h.onClose).toHaveBeenCalledOnce();
  });

  it('does not listen for outside presses while it is closed or after it is removed', () => {
    const h = handlers();
    const { rerender, unmount } = render(<InputHistoryPopup popup={popupState([entry('a')], 0, false)} {...h} />);

    fireEvent.mouseDown(document.body);
    expect(h.onClose).not.toHaveBeenCalled();

    rerender(<InputHistoryPopup popup={popupState([entry('a')])} {...h} />);
    unmount();
    fireEvent.mouseDown(document.body);

    expect(h.onClose).not.toHaveBeenCalled();
  });

  it('keeps the active entry in view as it changes, and does nothing while closed', () => {
    const h = handlers();
    const entries = [entry('a'), entry('b'), entry('c')];
    const { rerender } = render(<InputHistoryPopup popup={popupState(entries, 0, false)} {...h} />);
    expect(scrollIntoView).not.toHaveBeenCalled();

    rerender(<InputHistoryPopup popup={popupState(entries, 0)} {...h} />);
    expect(scrollIntoView.mock.contexts).toEqual([options()[0]]);
    expect(scrollIntoView).toHaveBeenLastCalledWith({ block: 'nearest' });

    rerender(<InputHistoryPopup popup={popupState(entries, 2)} {...h} />);
    expect(scrollIntoView.mock.contexts).toEqual([options()[0], options()[2]]);
  });
});
