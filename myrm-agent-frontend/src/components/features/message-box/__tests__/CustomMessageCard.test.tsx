import { describe, it, expect } from 'vitest';
import { expectNonNull } from '@/test-utils/expectDefined';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { CustomMessageCard } from '../CustomMessageCard';

describe('CustomMessageCard', () => {
  it('renders content, customType badge, and retention badge correctly', () => {
    render(
      <CustomMessageCard
        customType="code_analysis"
        content="AST parsed 42 source files"
        display={true}
        retention="persistent"
      />,
    );

    expect(screen.getByText('code_analysis')).toBeDefined();
    expect(screen.getByText('AST parsed 42 source files')).toBeDefined();
    expect(screen.getByText('Persistent')).toBeDefined();
  });

  it('renders ephemeral badge when retention is ephemeral', () => {
    render(
      <CustomMessageCard
        customType="rate_limit"
        content="Near rate limit warning"
        display={true}
        retention="ephemeral"
      />,
    );

    expect(screen.getByText('Ephemeral')).toBeDefined();
  });

  it('returns null when display is false', () => {
    const { container } = render(
      <CustomMessageCard customType="hidden_plugin" content="Should not be visible" display={false} />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('expands details drawer upon clicking Details button', () => {
    render(
      <CustomMessageCard
        customType="git_hook"
        content="Branch policy check passed"
        display={true}
        details={{ branch: 'main', commit: 'abc123' }}
      />,
    );

    expect(screen.queryByText(/abc123/)).toBeNull();

    const detailsBtn = screen.getByText('Details').closest('button');
    expect(detailsBtn?.getAttribute('aria-expanded')).toBe('false');
    expect(detailsBtn?.getAttribute('aria-controls')).toBe('custom-message-details');

    expectNonNull(detailsBtn, 'detailsBtn');
    fireEvent.click(detailsBtn);

    expect(detailsBtn?.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText(/abc123/)).toBeDefined();
  });

  it('renders formatted timestamp when timestamp prop is provided', () => {
    const testDate = new Date('2026-09-27T14:30:00Z');
    render(
      <CustomMessageCard customType="audit_log" content="Audit event recorded" display={true} timestamp={testDate} />,
    );

    // Formatted time string should be rendered in the document
    const timeRegex = /\d{1,2}:\d{2}/;
    expect(screen.getByText(timeRegex)).toBeDefined();
  });
});
