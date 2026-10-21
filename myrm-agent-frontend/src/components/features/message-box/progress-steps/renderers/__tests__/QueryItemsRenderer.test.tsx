import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import QueryItemsRenderer from '../QueryItemsRenderer';

describe('QueryItemsRenderer Component', () => {
  it('renders security CVE badge for CVE queries', () => {
    render(
      <QueryItemsRenderer
        items={[{ query: '"CVE-2024-38077" remote code execution' }]}
        messageId="msg-1"
        stepIndex={0}
      />,
    );
    expect(screen.getByText('Security CVE')).toBeDefined();
    expect(screen.getByText('"CVE-2024-38077" remote code execution')).toBeDefined();
  });

  it('renders academic DOI badge for DOI queries', () => {
    render(
      <QueryItemsRenderer
        items={[{ query: '"10.1038/s41586-024-07566-y" deepseek' }]}
        messageId="msg-2"
        stepIndex={1}
      />,
    );
    expect(screen.getByText('Academic DOI')).toBeDefined();
  });

  it('renders finance market badge for stock ticker queries', () => {
    render(
      <QueryItemsRenderer items={[{ query: 'NVDA stock earnings report 2026' }]} messageId="msg-3" stepIndex={2} />,
    );
    expect(screen.getByText('Finance Market')).toBeDefined();
  });

  it('renders code package badge for technical queries', () => {
    render(
      <QueryItemsRenderer items={[{ query: 'fastapi npm package alternative' }]} messageId="msg-4" stepIndex={3} />,
    );
    expect(screen.getByText('Code Package')).toBeDefined();
  });

  it('renders plain query without domain badge for general queries', () => {
    render(
      <QueryItemsRenderer items={[{ query: 'weather forecast beijing tomorrow' }]} messageId="msg-5" stepIndex={4} />,
    );
    expect(screen.queryByTestId('domain-intent-pill')).toBeNull();
    expect(screen.getByText('weather forecast beijing tomorrow')).toBeDefined();
  });
});
