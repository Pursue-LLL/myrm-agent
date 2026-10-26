/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { MockLocale } from '@/test-utils/realIntl';
import type { ImaStatus } from '@/services/wiki/ima';
import ImaSyncPanel from '../ImaSyncPanel';
import { UP_TO_DATE } from './imaFixtures';

const locale = vi.hoisted(() => ({ current: 'en' as MockLocale }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => locale.current));

function renderPanel(unreadable: ImaStatus['unreadable'], language: MockLocale = 'en') {
  locale.current = language;
  return render(
    <ImaSyncPanel
      status={{ ...UP_TO_DATE, unreadable }}
      busy={null}
      onSyncNow={vi.fn()}
      onPause={vi.fn()}
      onResume={vi.fn()}
      onCompile={vi.fn()}
      onOpenReport={vi.fn()}
    />,
  );
}

describe('ImaSyncPanel parts ima could not be read completely', () => {
  it('says nothing while everything could be read', () => {
    renderPanel([]);

    expect(screen.queryByText(/could not be read completely/)).not.toBeInTheDocument();
  });

  it('names the libraries in one sentence, in the reader language', () => {
    renderPanel([
      { kind: 'library', name: 'Research' },
      { kind: 'library', name: 'Recipes' },
    ]);
    expect(
      screen.getByText(/These knowledge bases could not be read completely.*Research and Recipes\./),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Your notes could not be read completely/)).not.toBeInTheDocument();
  });

  it('words the notes separately and never shows a raw code', () => {
    const { container } = renderPanel([{ kind: 'notes', name: '' }], 'zh');

    expect(screen.getByText(/笔记这次没能完整读取/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/notes_permission|unreadable|\{names\}/);
  });

  it('reports a library and the notes together', () => {
    renderPanel([
      { kind: 'library', name: 'Research' },
      { kind: 'notes', name: '' },
    ]);

    expect(screen.getByText(/Your notes could not be read completely/)).toBeInTheDocument();
    expect(screen.getByText(/These knowledge bases could not be read completely.*Research\./)).toBeInTheDocument();
  });
});
