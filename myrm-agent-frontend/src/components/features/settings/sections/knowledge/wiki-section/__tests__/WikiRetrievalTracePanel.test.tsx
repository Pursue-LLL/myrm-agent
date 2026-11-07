/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { WikiRetrievalTrace } from '@/services/wikiService';
import { resetKit } from './wikiSectionTestKit';
import { WikiRetrievalTracePanel } from '../WikiRetrievalTracePanel';

const EMPTY: WikiRetrievalTrace = { index_hits: [], seeds: [], sidecar_directories: [], selected_concepts: [] };

const HEADERS = [
  'query.retrievalTraceIndex',
  'query.retrievalTraceSidecar',
  'query.retrievalTraceSeeds',
  'query.retrievalTraceConcepts',
];

const seed = (name: string, source = 'vector') => ({ concept_name: name, score: 0.5, source });

function renderTrace(trace: WikiRetrievalTrace | null) {
  return render(<WikiRetrievalTracePanel retrievalTrace={trace} />);
}

const shownHeaders = () => HEADERS.filter((header) => screen.queryByText(header));

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiRetrievalTracePanel', () => {
  it.each([
    ['without a trace', null],
    ['for a trace with nothing in it', EMPTY],
  ])('renders nothing %s', (_label, trace) => {
    const { container } = renderTrace(trace);
    expect(container.childElementCount).toBe(0);
  });

  it('shows index hits as linked page names with their summaries', () => {
    renderTrace({
      ...EMPTY,
      index_hits: [
        { link_name: 'Alpha', summary: 'first page', score: 0.9 },
        { link_name: 'Beta', summary: 'second page', score: 0.8 },
      ],
    });
    expect(screen.getByText('query.retrievalTraceTitle')).toBeTruthy();
    expect(shownHeaders()).toEqual(['query.retrievalTraceIndex']);
    expect(screen.getByText('[[Alpha]] — first page')).toBeTruthy();
    expect(screen.getByText('[[Beta]] — second page')).toBeTruthy();
  });

  it('shows the sidecar directories on one line', () => {
    renderTrace({ ...EMPTY, sidecar_directories: ['raw/a', 'raw/b'] });
    expect(shownHeaders()).toEqual(['query.retrievalTraceSidecar']);
    expect(screen.getByText('raw/a · raw/b')).toBeTruthy();
  });

  it('shows each seed with the source that found it', () => {
    renderTrace({ ...EMPTY, seeds: [seed('Alpha', 'vector'), seed('Beta', 'keyword')] });
    expect(shownHeaders()).toEqual(['query.retrievalTraceSeeds']);
    expect(screen.getByText('Alpha (vector)')).toBeTruthy();
    expect(screen.getByText('Beta (keyword)')).toBeTruthy();
  });

  it('shows the first six seeds only', () => {
    renderTrace({ ...EMPTY, seeds: Array.from({ length: 8 }, (_, index) => seed(`Seed${index}`)) });
    const shown = screen.getAllByText(/^Seed\d \(vector\)$/).map((node) => node.textContent);
    expect(shown).toEqual(Array.from({ length: 6 }, (_, index) => `Seed${index} (vector)`));
  });

  it('shows the selected concepts on one line', () => {
    renderTrace({ ...EMPTY, selected_concepts: ['Alpha', 'Beta'] });
    expect(shownHeaders()).toEqual(['query.retrievalTraceConcepts']);
    expect(screen.getByText('Alpha · Beta')).toBeTruthy();
  });

  it('shows all four parts of a full trace in order', () => {
    renderTrace({
      index_hits: [{ link_name: 'Alpha', summary: 's', score: 1 }],
      seeds: [seed('Beta')],
      sidecar_directories: ['raw/a'],
      selected_concepts: ['Gamma'],
    });
    expect(shownHeaders()).toEqual(HEADERS);
    const order = [...document.querySelectorAll('.text-xs.font-medium')].map((node) => node.textContent);
    expect(order).toEqual([
      'query.retrievalTraceIndex',
      'query.retrievalTraceSidecar',
      'query.retrievalTraceSeeds',
      'query.retrievalTraceConcepts',
    ]);
  });
});
