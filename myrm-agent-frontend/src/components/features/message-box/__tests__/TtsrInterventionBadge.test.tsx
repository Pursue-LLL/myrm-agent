import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { TtsrInterventionBadge } from '../TtsrInterventionBadge';

describe('TtsrInterventionBadge', () => {
  it('renders rule name, 0-Tax badge, and retry indicator', () => {
    render(
      <TtsrInterventionBadge
        ruleId="ban_destructive_rm"
        ruleName="Ban Destructive Rm"
        reminder="Destructive rm commands are prohibited."
        target="assistant"
        retryCount={1}
        maxRetries={2}
      />
    );

    expect(screen.getByRole('status')).toBeDefined();
    expect(screen.getByText('Ban Destructive Rm')).toBeDefined();
    expect(screen.getByText('0-Tax Active')).toBeDefined();
    expect(screen.getByText('Retry 1/2')).toBeDefined();
  });

  it('expands and collapses guidance on toggle click', () => {
    render(
      <TtsrInterventionBadge
        ruleId="ban_leak"
        ruleName="Ban Secret Leak"
        reminder="Do not leak private tokens."
        target="tool_args"
      />
    );

    expect(screen.queryByText('Do not leak private tokens.')).toBeNull();

    const toggleBtn = screen.getByRole('button', { name: /View Guidance/i });
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(toggleBtn);

    expect(screen.getByText('Do not leak private tokens.')).toBeDefined();
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText(/Target Channel: tool_args/i)).toBeDefined();

    // Collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByText('Do not leak private tokens.')).toBeNull();
  });
});
