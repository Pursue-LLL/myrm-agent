/**
 * Unit tests for EpistemicBadge component.
 *
 * [INPUT] EpistemicBadge component, props
 * [OUTPUT] Vitest test suite verifying veracity tier rendering and compact mode.
 * [POS] Item 30 unit tests. Strictly under 120 lines. Zero `any`.
 */

import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EpistemicBadge } from './EpistemicBadge';

describe('EpistemicBadge', () => {
  it('renders assertion tier with default confidence score (100%)', () => {
    render(<EpistemicBadge tier="assertion" />);
    expect(screen.getByText('确定断言')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('renders observation tier with custom confidence score', () => {
    render(<EpistemicBadge tier="observation" confidenceScore={0.92} />);
    expect(screen.getByText('环境观察')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
  });

  it('renders belief tier with custom confidence score', () => {
    render(<EpistemicBadge tier="belief" confidenceScore={0.65} />);
    expect(screen.getByText('自主信念')).toBeInTheDocument();
    expect(screen.getByText('65%')).toBeInTheDocument();
  });

  it('renders compact mode with title attribute and without percent tag', () => {
    const { container } = render(<EpistemicBadge tier="belief" compact />);
    expect(screen.getByText('自主信念')).toBeInTheDocument();
    expect(screen.queryByText('60%')).not.toBeInTheDocument();
    expect(container.querySelector('[title*="自主信念"]')).toBeInTheDocument();
  });
});
