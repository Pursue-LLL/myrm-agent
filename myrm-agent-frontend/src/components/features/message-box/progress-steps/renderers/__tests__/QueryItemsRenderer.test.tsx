import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import QueryItemsRenderer from '../QueryItemsRenderer';

describe('QueryItemsRenderer Component', () => {
  it('renders each query verbatim, with no text added beside it', () => {
    const queries = [
      '"CVE-2024-38077" remote code execution',
      '"10.1038/s41586-024-07566-y" deepseek',
      'NVDA stock earnings report 2026',
      'weather forecast beijing tomorrow',
    ];
    render(<QueryItemsRenderer items={queries.map((query) => ({ query }))} messageId="msg-1" stepIndex={0} />);

    for (const query of queries) {
      expect(screen.getByTitle(query).textContent).toBe(query);
    }
  });
});
