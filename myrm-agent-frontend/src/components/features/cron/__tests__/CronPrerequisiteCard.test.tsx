import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CronPrerequisiteCard } from '../CronPrerequisiteCard';
import React from 'react';

// Mock next-intl useTranslations
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('CronPrerequisiteCard', () => {
  it('renders loading state correctly', () => {
    render(
      <CronPrerequisiteCard
        stats={null}
        loading={true}
        override={false}
        onOverrideChange={() => {}}
      />
    );
    expect(screen.getByText('checkingPrerequisite')).toBeDefined();
  });

  it('renders satisfied state when manual_success_count >= threshold', () => {
    render(
      <CronPrerequisiteCard
        stats={{
          fingerprint: '1234567890abcdef',
          manual_success_count: 2,
          threshold: 2,
          is_satisfied: true,
          chat_verified_count: 2,
          kanban_verified_count: 0,
          override_allowed: true,
        }}
        loading={false}
        override={false}
        onOverrideChange={() => {}}
      />
    );
    expect(screen.getByText('satisfiedTitle')).toBeDefined();
  });

  it('renders unmet state with override checkbox when not satisfied', () => {
    render(
      <CronPrerequisiteCard
        stats={{
          fingerprint: '1234567890abcdef',
          manual_success_count: 0,
          threshold: 2,
          is_satisfied: false,
          chat_verified_count: 0,
          kanban_verified_count: 0,
          override_allowed: true,
        }}
        loading={false}
        override={false}
        onOverrideChange={() => {}}
      />
    );
    expect(screen.getByText('unmetTitle')).toBeDefined();
    expect(screen.getByText('explicitOverrideLabel')).toBeDefined();
  });
});
