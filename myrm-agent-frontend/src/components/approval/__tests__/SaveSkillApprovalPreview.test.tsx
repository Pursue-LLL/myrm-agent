'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import SaveSkillApprovalPreview from '../SaveSkillApprovalPreview';

describe('SaveSkillApprovalPreview', () => {
  it('renders description, instructions, files, and footer', () => {
    render(
      <SaveSkillApprovalPreview
        toolInput={{
          description: 'Weekly digest skill',
          instructions: '# Weekly digest\nCollect metrics',
          files: ['scripts/run.py'],
        }}
        showFullInstructionsLabel="Show full"
        showLessLabel="Show less"
        showAllLinesLabel="Show all {count} lines"
        footerText="Footer copy"
      />,
    );

    expect(screen.getByTestId('save-skill-approval-preview')).toBeInTheDocument();
    expect(screen.getByText('Weekly digest skill')).toBeInTheDocument();
    expect(screen.getByText(/Collect metrics/)).toBeInTheDocument();
    expect(screen.getByTestId('skill-bundle-files')).toBeInTheDocument();
    expect(screen.getByText('run.py')).toBeInTheDocument();
    expect(screen.getByText('Footer copy')).toBeInTheDocument();
  });

  it('renders harness skill_manage content as instructions', () => {
    render(
      <SaveSkillApprovalPreview
        toolInput={{
          action: 'save',
          name: 'demo',
          content: '# Demo skill body',
        }}
        showFullInstructionsLabel="Show full"
        showLessLabel="Show less"
        showAllLinesLabel="Show all {count} lines"
        footerText="Footer copy"
      />,
    );

    expect(screen.getByText('# Demo skill body')).toBeInTheDocument();
  });
});
