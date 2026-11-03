/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MockLocale } from '@/test-utils/realIntl';

const { intl } = vi.hoisted(() => ({ intl: { locale: 'en' as MockLocale } }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import { DestructiveConfirmationBanner } from '../DestructiveConfirmationBanner';

const blastRadius = { impact_scope: 'workspace', affected_targets: ['/workspace/build'] };

describe('DestructiveConfirmationBanner copy', () => {
  beforeEach(() => {
    intl.locale = 'en';
  });

  it('names the affected targets in English', () => {
    render(<DestructiveConfirmationBanner blastRadius={blastRadius} onConfirmationChange={vi.fn()} />);

    expect(screen.getByText('Target paths / affected objects:')).toBeInTheDocument();
    expect(screen.getByText('/workspace/build')).toBeInTheDocument();
  });

  it('names the affected targets in Chinese', () => {
    intl.locale = 'zh';
    render(<DestructiveConfirmationBanner blastRadius={blastRadius} onConfirmationChange={vi.fn()} />);

    expect(screen.getByText('目标路径 / 影响对象：')).toBeInTheDocument();
  });

  it('confirms readiness in the current language once the keyword is typed', () => {
    const onConfirmationChange = vi.fn();
    render(<DestructiveConfirmationBanner blastRadius={blastRadius} onConfirmationChange={onConfirmationChange} />);
    expect(screen.queryByText('Ready')).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('CONFIRM'), { target: { value: 'CONFIRM' } });

    expect(onConfirmationChange).toHaveBeenLastCalledWith(true);
    expect(screen.getByText('Ready')).toBeInTheDocument();
  });

  it('shows the Chinese readiness label without an English duplicate', () => {
    intl.locale = 'zh';
    render(<DestructiveConfirmationBanner blastRadius={blastRadius} onConfirmationChange={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText('CONFIRM'), { target: { value: 'CONFIRM' } });

    expect(screen.getByText('已就绪')).toBeInTheDocument();
    expect(screen.queryByText(/Ready/)).not.toBeInTheDocument();
  });
});
