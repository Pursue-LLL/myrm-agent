import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PrivacyActionRow } from '../PrivacyActionRow';
import type { PIIAction } from '@/services/config/types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('PrivacyActionRow', () => {
  it.each<PIIAction>(['warn', 'pseudonymize', 'redact', 'block'])('explains what %s does to the text', (action) => {
    render(<PrivacyActionRow icon={null} label="S2" value={action} onChange={() => {}} />);

    expect(screen.getByText(`consequence.${action}`)).toBeTruthy();
    expect(screen.getByText('S2')).toBeTruthy();
  });

  it('shows the chosen action in the select', () => {
    render(<PrivacyActionRow icon={null} label="S3" value="redact" onChange={() => {}} />);

    expect(screen.getByRole('combobox').textContent).toContain('actionRedact');
  });
});
