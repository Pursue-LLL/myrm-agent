import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { InteractiveUIRenderer } from '../InteractiveUIRenderer';
import type { UIArtifact } from '@/store/chat/types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const artifact: UIArtifact = {
  surface_id: 's1',
  title: 'E2E_UPDATE_MARKER_ALPHA',
  components: [
    { id: 'txt', type: 'text', props: { variant: 'body' }, children: [], bindings: { text: '$.status' }, events: {} },
    { id: 'badge', type: 'badge', props: {}, children: [], bindings: { text: '$.badge' }, events: {} },
    { id: 'btn', type: 'button', props: { variant: 'primary' }, children: [], bindings: { label: '$.actionLabel' }, events: {} },
  ],
  root_ids: ['txt', 'badge', 'btn'],
  data: { status: 'E2E_UPDATE_INITIAL', badge: 'In Progress', actionLabel: 'Retry' },
  actions: [],
};

describe('InteractiveUIRenderer bindings', () => {
  it('renders bound values for display components (text/badge/button)', () => {
    render(<InteractiveUIRenderer artifact={artifact} />);
    expect(screen.getByText('E2E_UPDATE_INITIAL')).toBeInTheDocument();
    expect(screen.getByText('In Progress')).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('re-renders with updated data when artifact.data changes (update_ui_data)', () => {
    const { rerender } = render(<InteractiveUIRenderer artifact={artifact} />);
    expect(screen.getByText('E2E_UPDATE_INITIAL')).toBeInTheDocument();

    const updated: UIArtifact = {
      ...artifact,
      data: { status: 'E2E_UPDATE_FINAL', badge: 'Complete', actionLabel: 'Retry' },
    };
    rerender(<InteractiveUIRenderer artifact={updated} />);
    expect(screen.getByText('E2E_UPDATE_FINAL')).toBeInTheDocument();
    expect(screen.queryByText('E2E_UPDATE_INITIAL')).not.toBeInTheDocument();
  });

  it('keeps static props when no binding resolves (fallback to props)', () => {
    const staticArtifact: UIArtifact = {
      ...artifact,
      components: [
        { id: 'txt', type: 'text', props: { text: 'Static Title' }, children: [], bindings: {}, events: {} },
      ],
      root_ids: ['txt'],
      data: {},
    };
    render(<InteractiveUIRenderer artifact={staticArtifact} />);
    expect(screen.getByText('Static Title')).toBeInTheDocument();
  });
});
