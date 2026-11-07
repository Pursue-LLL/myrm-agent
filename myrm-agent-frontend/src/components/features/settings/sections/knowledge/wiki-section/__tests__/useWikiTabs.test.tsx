/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { currentQuery, resetKit, router, setQuery } from './wikiSectionTestKit';
import { useWikiTabs } from '../useWikiTabs';

const scrollIntoView = vi.fn();

function setup(query = '') {
  setQuery(query);
  return renderHook(() => useWikiTabs());
}

const params = () => new URLSearchParams(currentQuery());

beforeEach(() => {
  resetKit();
  scrollIntoView.mockClear();
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    writable: true,
    value: scrollIntoView,
  });
});

afterEach(cleanup);

describe('useWikiTabs: reading the URL', () => {
  it('opens on the overview with nothing selected', () => {
    const { result } = setup();
    expect(result.current.activeTab).toBe('overview');
    expect(result.current.pendingEditsInitialFilter).toBe('all');
    expect(result.current.rawPathFromUrl).toBeNull();
    expect(result.current.conceptPathFromUrl).toBeNull();
  });

  it.each(['concepts', 'pendingEdits', 'duplicateReview', 'queue', 'overview'])(
    'opens the %s tab named by ?wikiTab=',
    (tab) => {
      expect(setup(`wikiTab=${tab}`).result.current.activeTab).toBe(tab);
    },
  );

  it('ignores a tab name it does not know', () => {
    expect(setup('wikiTab=bogus').result.current.activeTab).toBe('overview');
  });

  it('opens the concepts tab for a deep link to a concept', () => {
    const { result } = setup('conceptPath=topics%2Fa');
    expect(result.current.activeTab).toBe('concepts');
    expect(result.current.conceptPathFromUrl).toBe('topics/a');
  });

  it('lets an explicit tab win over the concept deep link', () => {
    expect(setup('wikiTab=queue&conceptPath=topics%2Fa').result.current.activeTab).toBe('queue');
  });

  it('exposes the raw file the URL points at', () => {
    expect(setup('rawPath=notes%2Fb.md').result.current.rawPathFromUrl).toBe('notes/b.md');
  });

  it('returns to the overview when the URL drops the tab', () => {
    const { result } = setup('wikiTab=queue');
    setQuery('');
    expect(result.current.activeTab).toBe('overview');
  });

  it('follows the URL when it moves to another tab', () => {
    const { result } = setup('wikiTab=queue');
    setQuery('wikiTab=concepts');
    expect(result.current.activeTab).toBe('concepts');
  });

  it('keeps the current tab when the URL later names a tab it does not know', () => {
    const { result } = setup('wikiTab=queue');
    setQuery('wikiTab=bogus');
    expect(result.current.activeTab).toBe('queue');
  });
});

describe('useWikiTabs: focus=wikiignore', () => {
  it('scrolls the ignore panel into view', () => {
    const panel = document.createElement('div');
    panel.id = 'wiki-wikiignore-panel';
    document.body.append(panel);
    try {
      setup('focus=wikiignore');
      expect(scrollIntoView).toHaveBeenCalledExactlyOnceWith({ behavior: 'smooth', block: 'start' });
      expect(scrollIntoView.mock.contexts[0]).toBe(panel);
    } finally {
      panel.remove();
    }
  });

  it('scrolls when the URL asks for it after the page has opened', () => {
    const panel = document.createElement('div');
    panel.id = 'wiki-wikiignore-panel';
    document.body.append(panel);
    try {
      setup();
      expect(scrollIntoView).not.toHaveBeenCalled();
      setQuery('focus=wikiignore');
      expect(scrollIntoView).toHaveBeenCalledOnce();
    } finally {
      panel.remove();
    }
  });

  it('does nothing when the panel is not on the page', () => {
    expect(() => setup('focus=wikiignore')).not.toThrow();
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('does nothing for any other focus value', () => {
    const panel = document.createElement('div');
    panel.id = 'wiki-wikiignore-panel';
    document.body.append(panel);
    try {
      setup('focus=something');
      expect(scrollIntoView).not.toHaveBeenCalled();
    } finally {
      panel.remove();
    }
  });
});

describe('useWikiTabs: changing tab', () => {
  it('switches the tab and writes it to the URL without scrolling the page', () => {
    const { result } = setup('agentId=a1');
    act(() => result.current.handleWikiTabChange('concepts'));
    expect(result.current.activeTab).toBe('concepts');
    expect(router.replace).toHaveBeenLastCalledWith('/settings/wiki?agentId=a1&wikiTab=concepts', { scroll: false });
  });

  it('removes the tab from the URL when going back to the overview', () => {
    const { result } = setup('agentId=a1&wikiTab=queue');
    act(() => result.current.handleWikiTabChange('overview'));
    expect(result.current.activeTab).toBe('overview');
    expect(router.replace).toHaveBeenLastCalledWith('/settings/wiki?agentId=a1', { scroll: false });
  });

  it('writes the bare path when nothing is left in the query', () => {
    const { result } = setup('wikiTab=queue');
    act(() => result.current.handleWikiTabChange('overview'));
    expect(router.replace).toHaveBeenLastCalledWith('/settings/wiki', { scroll: false });
  });

  it('ignores a tab it does not know', () => {
    const { result } = setup();
    act(() => result.current.handleWikiTabChange('bogus'));
    expect(result.current.activeTab).toBe('overview');
    expect(router.replace).not.toHaveBeenCalled();
  });

  it('writes the tab onto the query the page has now, not the one it opened with', () => {
    const { result } = setup('agentId=a1');
    setQuery('agentId=a2');
    act(() => result.current.handleWikiTabChange('concepts'));
    expect(router.replace).toHaveBeenLastCalledWith('/settings/wiki?agentId=a2&wikiTab=concepts', { scroll: false });
  });
});

describe('useWikiTabs: before the router has caught up', () => {
  // The router applies a replace later; the tab the user asked for must not wait for it.
  const holdRouter = () => router.replace.mockImplementationOnce(() => undefined);

  it('switches the tab at once', () => {
    const { result } = setup();
    holdRouter();
    act(() => result.current.handleWikiTabChange('queue'));
    expect(result.current.activeTab).toBe('queue');
  });

  it('opens a concept at once', () => {
    const { result } = setup();
    holdRouter();
    act(() => result.current.openConcept('topics/a'));
    expect(result.current.activeTab).toBe('concepts');
  });

  it.each([
    ['a concept page', 'concepts/topics/a.md', 'wikiTab=queue', 'concepts'],
    ['a raw file', 'raw/notes/b.md', 'wikiTab=concepts', 'overview'],
  ])('shows a health issue in %s at once', (_label, location, opened, expected) => {
    const { result } = setup(opened);
    holdRouter();
    act(() => result.current.navigateToHealthIssue(location));
    expect(result.current.activeTab).toBe(expected);
  });
});

describe('useWikiTabs: jumping from another panel', () => {
  it('opens a concept on the concepts tab and keeps the agent scope', () => {
    const { result } = setup('agentId=a1');
    act(() => result.current.openConcept('topics/a'));
    expect(result.current.activeTab).toBe('concepts');
    expect(params().get('wikiTab')).toBe('concepts');
    expect(params().get('conceptPath')).toBe('topics/a');
    expect(params().get('agentId')).toBe('a1');
    expect(router.replace).toHaveBeenLastCalledWith(expect.any(String), { scroll: false });
  });

  it('sends a health issue in a concept page to the concepts tab', () => {
    const { result } = setup('agentId=a1&rawPath=old.md&conceptPath=older');
    act(() => result.current.navigateToHealthIssue('concepts/topics/a.md'));
    expect(result.current.activeTab).toBe('concepts');
    expect(params().get('wikiTab')).toBe('concepts');
    expect(params().get('conceptPath')).toBe('topics/a');
    expect(params().has('rawPath')).toBe(false);
    expect(params().get('agentId')).toBe('a1');
  });

  it('sends a health issue in a raw file to the overview with that file highlighted', () => {
    const { result } = setup('agentId=a1&wikiTab=concepts&conceptPath=older');
    act(() => result.current.navigateToHealthIssue('raw/notes/b.md'));
    expect(result.current.activeTab).toBe('overview');
    expect(params().get('rawPath')).toBe('notes/b.md');
    expect(params().has('wikiTab')).toBe(false);
    expect(params().has('conceptPath')).toBe(false);
    expect(params().get('agentId')).toBe('a1');
    expect(result.current.rawPathFromUrl).toBe('notes/b.md');
  });

  it('opens the pending edits filtered to synthesis pages', () => {
    const { result } = setup();
    act(() => result.current.handleOpenSynthesisPending());
    expect(result.current.activeTab).toBe('pendingEdits');
    expect(result.current.pendingEditsInitialFilter).toBe('synthesis');
    expect(params().get('wikiTab')).toBe('pendingEdits');
  });

  it('opens the duplicate review without touching the pending edits filter', () => {
    const { result } = setup();
    act(() => result.current.handleOpenDuplicateReview());
    expect(result.current.activeTab).toBe('duplicateReview');
    expect(result.current.pendingEditsInitialFilter).toBe('all');
    expect(params().get('wikiTab')).toBe('duplicateReview');
  });
});
