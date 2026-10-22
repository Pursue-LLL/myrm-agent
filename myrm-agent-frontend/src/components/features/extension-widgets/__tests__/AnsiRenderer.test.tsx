import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AnsiRenderer } from '../AnsiRenderer';

describe('AnsiRenderer', () => {
  it('renders null when raw input is empty', () => {
    const { container } = render(<AnsiRenderer raw="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders styled text elements correctly', () => {
    const raw = '\x1b[32mSuccess message\x1b[0m normal text';
    render(<AnsiRenderer raw={raw} />);

    expect(screen.getByTestId('ansi-renderer-container')).toBeInTheDocument();
    const greenText = screen.getByText('Success message');
    expect(greenText).toBeInTheDocument();
    expect(greenText).toHaveStyle({ color: 'rgb(74, 222, 128)' }); // #4ade80

    expect(screen.getByText(/normal text/)).toBeInTheDocument();
  });
});
