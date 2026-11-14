/** @vitest-environment jsdom */
import type { ReactNode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import useResearchStore from '@/store/useResearchStore';
import ResourcePoolPanel from '../ResourcePoolPanel';

// Resolves to "key" or "key:name" so assertions can read which message and which resource a label is built from.
const stableT = (key: string, values?: { name?: string }) => (values?.name ? `${key}:${values.name}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/wikiService', () => ({ wikiService: { listConcepts: vi.fn() } }));
vi.mock('@/services/file', () => ({ uploadFiles: vi.fn() }));
vi.mock('@/services/uploadController', () => ({ resetUploadController: vi.fn(), getUploadSignal: vi.fn() }));
// jsdom has neither ResizeObserver (Radix scroll area) nor a tooltip provider; pass-through stubs keep the list under test.
vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: () => null,
}));

describe('ResourcePoolPanel resource rows', () => {
  beforeEach(() => {
    act(() => {
      useResearchStore.getState().reset();
      useResearchStore.getState().addResource({ id: 'concept:quantum', name: 'quantum', type: 'concept' });
    });
  });

  it('names the select toggle and the remove button after the resource they act on', () => {
    render(<ResourcePoolPanel />);

    expect(screen.getByRole('button', { name: 'deselectResource:quantum' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'removeResource:quantum' })).toBeInTheDocument();
  });

  it('flips the toggle label once the resource is deselected', () => {
    render(<ResourcePoolPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'deselectResource:quantum' }));

    expect(useResearchStore.getState().resources[0]?.selected).toBe(false);
    expect(screen.getByRole('button', { name: 'selectResource:quantum' })).toBeInTheDocument();
  });

  it('removes the resource from the remove button without toggling it first', () => {
    render(<ResourcePoolPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'removeResource:quantum' }));

    expect(useResearchStore.getState().resources).toHaveLength(0);
  });
});
