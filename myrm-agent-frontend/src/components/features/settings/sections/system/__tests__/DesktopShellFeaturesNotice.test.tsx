/** @vitest-environment jsdom */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const isTauriRuntimeMock = vi.fn(() => false);

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => isTauriRuntimeMock(),
}));

import DesktopShellFeaturesNotice from '../DesktopShellFeaturesNotice';

describe('DesktopShellFeaturesNotice', () => {
  beforeEach(() => {
    isTauriRuntimeMock.mockReturnValue(false);
  });

  it('renders in browser mode', () => {
    render(<DesktopShellFeaturesNotice />);
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('headline')).toBeInTheDocument();
  });

  it('hidden in Tauri runtime', () => {
    isTauriRuntimeMock.mockReturnValue(true);
    const { container } = render(<DesktopShellFeaturesNotice />);
    expect(container).toBeEmptyDOMElement();
  });
});
