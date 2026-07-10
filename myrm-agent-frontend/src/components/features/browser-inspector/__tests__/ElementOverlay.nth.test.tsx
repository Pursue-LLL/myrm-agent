'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ElementOverlay from '../ElementOverlay';
import type { BrowserRefInfo } from '@/store/chat/types';

const viewport = { width: 400, height: 300 };

function makeRef(
  role: string,
  nth: number | undefined,
  id: string,
): [string, BrowserRefInfo] {
  return [
    id,
    {
      role,
      name: role,
      nth,
      bbox: {
        x: 40,
        y: 40,
        width: 80,
        height: 40,
        centerX: 80,
        centerY: 60,
        viewport_width: viewport.width,
        viewport_height: viewport.height,
      },
    },
  ];
}

describe('ElementOverlay SOM nth badges', () => {
  it('renders nth corner labels for interactive refs', () => {
    const refs = Object.fromEntries([
      makeRef('button', 1, 'd1'),
      makeRef('textbox', 2, 'd2'),
    ]);

    render(
      <div style={{ width: 400, height: 300, position: 'relative' }}>
        <ElementOverlay
          refs={refs}
          imageWidth={400}
          imageHeight={300}
          viewportWidth={viewport.width}
          viewportHeight={viewport.height}
          selectedRefId={null}
          onElementClick={vi.fn()}
        />
      </div>,
    );

    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('omits nth badge when nth is null', () => {
    const refs = Object.fromEntries([makeRef('button', undefined, 'd1')]);

    render(
      <ElementOverlay
        refs={refs}
        imageWidth={400}
        imageHeight={300}
        viewportWidth={viewport.width}
        viewportHeight={viewport.height}
        selectedRefId={null}
        onElementClick={vi.fn()}
      />,
    );

    const button = screen.getByRole('button', { name: /Select element d1/i });
    expect(button).toHaveAttribute('title', '[d1] button: button');
    expect(screen.queryByText('1')).not.toBeInTheDocument();
  });

  it('includes nth in title tooltip when present', () => {
    const refs = Object.fromEntries([makeRef('button', 5, 'd5')]);

    render(
      <ElementOverlay
        refs={refs}
        imageWidth={400}
        imageHeight={300}
        viewportWidth={viewport.width}
        viewportHeight={viewport.height}
        selectedRefId={null}
        onElementClick={vi.fn()}
      />,
    );

    const button = screen.getByRole('button', { name: /Select element d5/i });
    expect(button).toHaveAttribute('title', '[5] [d5] button: button');
  });

  it('calls onElementClick with ref id', () => {
    const onElementClick = vi.fn();
    const refs = Object.fromEntries([makeRef('button', 1, 'd1')]);

    render(
      <ElementOverlay
        refs={refs}
        imageWidth={400}
        imageHeight={300}
        viewportWidth={viewport.width}
        viewportHeight={viewport.height}
        selectedRefId={null}
        onElementClick={onElementClick}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Select element d1/i }));
    expect(onElementClick).toHaveBeenCalledWith('d1', refs.d1);
  });
});
