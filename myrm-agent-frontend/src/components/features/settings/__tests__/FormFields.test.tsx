/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MockLocale } from '@/test-utils/realIntl';

const { intl } = vi.hoisted(() => ({ intl: { locale: 'en' as MockLocale } }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import { TextareaField } from '../FormFields';

describe('TextareaField confirm button', () => {
  beforeEach(() => {
    intl.locale = 'en';
  });

  it('is labelled in the interface language', () => {
    render(<TextareaField label="Notes" value="" onChange={vi.fn()} showConfirmButton />);

    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
  });

  it('follows a language switch', () => {
    intl.locale = 'zh';
    render(<TextareaField label="Notes" value="" onChange={vi.fn()} showConfirmButton />);

    expect(screen.getByRole('button', { name: '确定' })).toBeInTheDocument();
  });

  it('shows no button unless requested', () => {
    render(<TextareaField label="Notes" value="" onChange={vi.fn()} />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
