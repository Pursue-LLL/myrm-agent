/**
 * [INPUT]
 * - @/components/features/settings/sections/system/UnattendedDesktopGuideCard
 *
 * [OUTPUT]
 * - vitest: Tauri gate + step labels
 *
 * [POS]
 * Smoke tests for unattended desktop setup guide card.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import UnattendedDesktopGuideCard from '../UnattendedDesktopGuideCard';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const isTauriMock = vi.fn(() => true);

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => isTauriMock(),
}));

describe('UnattendedDesktopGuideCard', () => {
  it('does not render outside Tauri', () => {
    isTauriMock.mockReturnValueOnce(false);
    const { container } = render(
      <UnattendedDesktopGuideCard privacyCurtainEnabled={false} lockedUseEnabled={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders guide title and steps in Tauri', () => {
    isTauriMock.mockReturnValue(true);
    render(<UnattendedDesktopGuideCard privacyCurtainEnabled lockedUseEnabled={false} />);

    expect(screen.getByText('guideTitle')).toBeInTheDocument();
    expect(screen.getByText('stepCurtainTitle')).toBeInTheDocument();
    expect(screen.getByText('stepLockedUseTitle')).toBeInTheDocument();
    expect(screen.getByText('stepApprovalTitle')).toBeInTheDocument();
  });
});
