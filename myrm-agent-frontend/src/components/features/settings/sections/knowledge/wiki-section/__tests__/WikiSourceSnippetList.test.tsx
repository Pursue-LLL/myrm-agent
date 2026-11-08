/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { WikiSourceSnippet } from '@/services/wikiService';
import { click, resetKit } from './wikiSectionTestKit';
import { snippetOf } from './wikiSectionFixtures';
import { WikiSourceSnippetList } from '../WikiSourceSnippetList';

function renderList(snippets: WikiSourceSnippet[], scope: string | null = null) {
  const onOpenSnippet = vi.fn();
  const { container } = render(
    <WikiSourceSnippetList sourceSnippets={snippets} agentScopeId={scope} onOpenSnippet={onOpenSnippet} />,
  );
  return { onOpenSnippet, container };
}

const card = () => screen.getByRole('button');

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiSourceSnippetList: the list', () => {
  it('renders nothing without snippets', () => {
    const { container } = renderList([]);
    expect(container.childElementCount).toBe(0);
  });

  it('lists every snippet under the sources heading, even when two share a path', () => {
    renderList([snippetOf({ name: 'First' }), snippetOf({ name: 'Second' })]);
    expect(screen.getByText('sources_title')).toBeTruthy();
    expect(screen.getAllByRole('button').map((button) => button.querySelector('span')?.textContent)).toEqual([
      'First',
      'Second',
    ]);
  });

  it('titles a snippet without a name by its path', () => {
    renderList([snippetOf({ name: '', path: 'concepts/untitled.md' })]);
    expect(screen.getAllByText('concepts/untitled.md')).toHaveLength(2);
  });
});

describe('WikiSourceSnippetList: what a card shows', () => {
  it.each([
    ['L0', 'kb_level_l0'],
    ['L1', 'kb_level_l1'],
    ['L2', 'kb_level_l2'],
  ] as const)('shows the %s level as %s', (level, label) => {
    renderList([snippetOf({ level })]);
    expect(screen.getByText(label)).toBeTruthy();
  });

  it('shows no level for a level it does not know', () => {
    renderList([snippetOf({ level: 'L9' as WikiSourceSnippet['level'] })]);
    expect(screen.queryByText(/^kb_level/)).toBeNull();
  });

  it.each([
    ['index_routing', 'kb_section_index_routing'],
    ['summary', 'summary'],
  ])('shows the section %s as %s', (section, label) => {
    renderList([snippetOf({ section })]);
    expect(screen.getByText(label)).toBeTruthy();
  });

  it('shows no section line without a section', () => {
    renderList([snippetOf({ section: '' })]);
    expect(card().querySelector('.mt-1.text-xs')).toBeNull();
  });

  it('shows the path and the excerpt when there are any', () => {
    renderList([snippetOf({ path: 'concepts/a.md', snippet: 'the excerpt' })]);
    expect(screen.getByText('concepts/a.md')).toBeTruthy();
    expect(screen.getByText('the excerpt')).toBeTruthy();
  });

  it('leaves out an empty path and an empty excerpt', () => {
    renderList([snippetOf({ name: 'Named', path: '', snippet: '' })]);
    expect(card().querySelector('.font-mono')).toBeNull();
    expect(card().querySelector('p')).toBeNull();
  });
});

describe('WikiSourceSnippetList: claim evidence', () => {
  it('shows where a claim is evidenced, with its line range', () => {
    renderList([snippetOf({ claim_id: 'c1', evidence_path: 'raw/a.md', line_range: '3-9' })]);
    expect(screen.getByText('raw/a.md · L3-9')).toBeTruthy();
  });

  it('shows only the evidence path when there is no line range', () => {
    renderList([snippetOf({ claim_id: 'c1', evidence_path: 'raw/a.md' })]);
    expect(screen.getByText('raw/a.md')).toBeTruthy();
  });

  it('shows no evidence line for a snippet without a claim', () => {
    renderList([snippetOf({ evidence_path: 'raw/a.md', line_range: '3-9' })]);
    expect(screen.queryByText(/raw\/a\.md/)).toBeNull();
  });

  it.each([
    ['verified', { evidence_path: 'raw/a.md' }, 'evidenceSnapshotVerified'],
    ['stale', { evidence_path: 'raw/a.md' }, 'evidenceSnapshotStale'],
    ['missing', { evidence_path: 'raw/a.md' }, 'evidenceSnapshotMissing'],
  ] as const)('says a %s snapshot is %s', (status, extra, label) => {
    renderList([snippetOf({ snapshot_status: status, ...extra })]);
    expect(screen.getAllByText(/^evidenceSnapshot/).map((node) => node.textContent)).toEqual([label]);
  });

  it('says nothing about a missing snapshot that has no evidence path', () => {
    renderList([snippetOf({ snapshot_status: 'missing' })]);
    expect(screen.queryByText(/^evidenceSnapshot/)).toBeNull();
  });

  it('says nothing when the snapshot status is unknown', () => {
    renderList([snippetOf()]);
    expect(screen.queryByText(/^evidenceSnapshot/)).toBeNull();
  });
});

describe('WikiSourceSnippetList: asset thumbnails', () => {
  it('shows a thumbnail served for the scope of the page', () => {
    renderList([snippetOf({ hit_kind: 'asset', asset_filename: 'my chart.png' })], 'a1');
    expect(document.querySelector('img')?.getAttribute('src')).toBe(
      'http://api.test/wiki/assets/my%20chart.png?agent_id=a1',
    );
  });

  it('serves the thumbnail of the default scope without an agent', () => {
    renderList([snippetOf({ hit_kind: 'asset', asset_filename: 'chart.png' })]);
    expect(document.querySelector('img')?.getAttribute('src')).toBe('http://api.test/wiki/assets/chart.png');
  });

  it.each([
    ['a concept hit', { hit_kind: 'concept', asset_filename: 'chart.png' }],
    ['an asset hit without a file name', { hit_kind: 'asset' }],
    ['a hit of unknown kind', {}],
  ] as const)('shows no thumbnail for %s', (_label, extra) => {
    renderList([snippetOf(extra)]);
    expect(document.querySelector('img')).toBeNull();
  });
});

describe('WikiSourceSnippetList: opening a snippet', () => {
  it('hands everything about a snippet to the drawer', async () => {
    const { onOpenSnippet } = renderList(
      [
        snippetOf({
          name: 'Concept A',
          section: 'index_routing',
          snippet: 'the excerpt',
          level: 'L2',
          snapshot_status: 'stale',
          claim_status: 'contested',
          claim_confidence: 0.4,
          claim_text: 'the claim',
          resource_uri: 'wiki://a',
          superseded_from_uri: 'wiki://old-a',
          hit_kind: 'asset',
          asset_filename: 'chart.png',
        }),
      ],
      'a1',
    );
    await click(card());
    expect(onOpenSnippet).toHaveBeenCalledExactlyOnceWith({
      open: true,
      title: 'Concept A',
      section: 'kb_section_index_routing',
      snippet: 'the excerpt',
      level: 'L2',
      snapshotStatus: 'stale',
      claimStatus: 'contested',
      claimConfidence: 0.4,
      claimText: 'the claim',
      resourceUri: 'wiki://a',
      supersededFromUri: 'wiki://old-a',
      thumbnailUrl: 'http://api.test/wiki/assets/chart.png?agent_id=a1',
    });
  });

  it('hands over a plain concept hit with no thumbnail and no level it cannot name', async () => {
    const { onOpenSnippet } = renderList([
      snippetOf({ name: '', path: 'concepts/a.md', section: '', level: 'L9' as WikiSourceSnippet['level'] }),
    ]);
    await click(card());
    expect(onOpenSnippet).toHaveBeenCalledExactlyOnceWith({
      open: true,
      title: 'concepts/a.md',
      section: undefined,
      snippet: 'a snippet of the concept',
      level: undefined,
      snapshotStatus: undefined,
      claimStatus: undefined,
      claimConfidence: undefined,
      claimText: undefined,
      resourceUri: undefined,
      supersededFromUri: undefined,
      thumbnailUrl: null,
    });
  });

  it('opens only the snippet that was clicked', async () => {
    const { onOpenSnippet } = renderList([snippetOf({ name: 'First' }), snippetOf({ name: 'Second' })]);
    await click(screen.getAllByRole('button')[1]);
    expect(onOpenSnippet).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ title: 'Second' }));
  });
});
