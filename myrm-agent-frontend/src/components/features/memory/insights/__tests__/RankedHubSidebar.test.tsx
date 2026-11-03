/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RankedHubSidebar } from '../RankedHubSidebar';

describe('RankedHubSidebar accessible name', () => {
  it('labels the sidebar landmark from translations', () => {
    render(<RankedHubSidebar hubs={[]} onSelectHub={vi.fn()} onHoverHub={vi.fn()} />);

    expect(screen.getByRole('complementary', { name: 'rankedHubSidebarLabel' })).toBeInTheDocument();
  });
});
