'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ElementOverlay from '@/components/features/browser-inspector/ElementOverlay';
import type { BrowserRefInfo } from '@/store/chat/types';

function makeRef(overrides: Partial<NonNullable<BrowserRefInfo['bbox']>>): BrowserRefInfo {
  return {
    role: 'button',
    name: 'Add to cart',
    nth: 1,
    position: null,
    bbox: {
      x: 100,
      y: 200,
      width: 80,
      height: 32,
      centerX: 140,
      centerY: 216,
      viewport_width: 1280,
      viewport_height: 720,
      ...overrides,
    },
  };
}

describe('ElementOverlay geometry', () => {
  const viewportWidth = 1280;
  const viewportHeight = 720;

  it('uses viewport-relative coordinates so a scrolled page overlay aligns with the viewport screenshot', () => {
    // Browser: element is scrolled 300px down the page; viewport coords differ from absolute coords.
    const refs = {
      addToCart: makeRef({
        x: 100,
        y: 500,
        viewport_x: 100,
        viewport_y: 200,
      }),
    };

    render(
      <ElementOverlay
        refs={refs}
        imageWidth={viewportWidth}
        imageHeight={viewportHeight}
        viewportWidth={viewportWidth}
        viewportHeight={viewportHeight}
        selectedRefId={null}
        onElementClick={() => undefined}
      />,
    );

    const button = screen.getByRole('button', { name: /Add to cart/i });
    // scale = 1: viewport_y (200) is used, not absolute y (500).
    expect(button).toHaveStyle({
      left: '100px',
      top: '200px',
      width: '80px',
      height: '32px',
    });
  });

  it('falls back to absolute coordinates when viewport fields are absent (desktop refs)', () => {
    const refs = {
      okButton: makeRef({
        x: 40,
        y: 60,
      }),
    };

    render(
      <ElementOverlay
        refs={refs}
        imageWidth={1280}
        imageHeight={720}
        viewportWidth={viewportWidth}
        viewportHeight={viewportHeight}
        selectedRefId={null}
        onElementClick={() => undefined}
      />,
    );

    const button = screen.getByRole('button', { name: /okButton|button/i });
    expect(button).toHaveStyle({
      left: '40px',
      top: '60px',
    });
  });
});
