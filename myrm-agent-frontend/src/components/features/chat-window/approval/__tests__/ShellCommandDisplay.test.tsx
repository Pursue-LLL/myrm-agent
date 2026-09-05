import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ShellCommandDisplay from '../ShellCommandDisplay';

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const messages: Record<string, string> = {
      'scriptOperand.protectedBadge': 'Script Content Protected',
      'scriptOperand.protectedTooltip': 'File content SHA-256 is anchored.',
      'scriptOperand.pathLabel': 'Script File',
      'scriptOperand.hashLabel': 'Content SHA-256',
      workspaceLabel: 'Workspace',
    };
    return (key: string) => messages[key] ?? key;
  },
  useLocale: () => 'en',
}));

describe('ShellCommandDisplay', () => {
  it('renders command text and tool name correctly', () => {
    render(
      <ShellCommandDisplay
        command="bash deploy.sh --stage prod"
        toolName="bash"
      />
    );

    expect(screen.getByText('$')).toBeDefined();
    expect(screen.getByText('bash')).toBeDefined();
    expect(screen.getByText('bash deploy.sh --stage prod')).toBeDefined();
    expect(screen.queryByText('Script Content Protected')).toBeNull();
  });

  it('renders script operand protected badge when scriptOperandHash is provided', () => {
    const mockHash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
    const mockPath = '/workspace/scripts/deploy.sh';

    render(
      <ShellCommandDisplay
        command="bash scripts/deploy.sh"
        toolName="bash"
        scriptOperandHash={mockHash}
        scriptOperandPath={mockPath}
      />
    );

    expect(screen.getByText('Script Content Protected')).toBeDefined();
    expect(screen.getByText('scripts/deploy.sh', { exact: false })).toBeDefined();
  });
});
