/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import BrandLogo from '../BrandLogo';

describe('BrandLogo', () => {
  it('names the mark after the brand when it stands alone', () => {
    render(<BrandLogo />);

    expect(screen.getByRole('img', { name: 'MyrmAgent' })).toBeTruthy();
  });

  it('drops its alt text when the brand name is written beside it, so a button reads the name once', () => {
    render(
      <button type="button">
        <BrandLogo decorative />
        <span>MyrmAgent</span>
      </button>,
    );

    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByRole('button', { name: 'MyrmAgent' })).toBeTruthy();
  });
});
