import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { WorkflowRecorderModal } from '../WorkflowRecorderModal';
import * as skillService from '@/services/skill/core';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params && 'count' in params) {
    return `${key} (${params.count})`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/skill/core', () => ({
  startDesktopRecording: vi.fn().mockResolvedValue({ session_id: 'rec-123', status: 'recording', started_at: 1000 }),
  stopDesktopRecording: vi.fn().mockResolvedValue({ session_id: 'rec-123', status: 'stopped', event_count: 2, duration_seconds: 5 }),
  recordDesktopEvent: vi.fn().mockResolvedValue({ status: 'ok', recorded_count: 1 }),
  analyzeDesktopPlan: vi.fn().mockResolvedValue({
    plan: {
      name: 'Test Workflow Skill',
      description: 'Automated test workflow',
      intent: 'Automates actions',
      steps: [
        {
          step_id: 'step-1',
          title: 'Switch to Excel',
          description: 'Activate Excel spreadsheet',
          target_app: 'Excel',
        },
      ],
      variables: { val_1: 'sample' },
      allowed_tools: ['shell_execute'],
    },
    event_count: 2,
    validation_errors: [],
  }),
  compileDesktopPlan: vi.fn().mockResolvedValue({
    markdown_content: '---\nname: test-workflow-skill\n---\n# Test Workflow Skill',
    validation_errors: [],
  }),
  publishDesktopSkill: vi.fn().mockResolvedValue({
    skill_id: 'test-workflow-skill',
    skill_name: 'Test Workflow Skill',
    status: 'published',
    file_path: '/skills/test-workflow-skill/SKILL.md',
  }),
}));

describe('WorkflowRecorderModal', () => {
  it('renders correctly and completes the recording, review and compilation cycle', async () => {
    const handleClose = vi.fn();
    const handlePublished = vi.fn();

    render(
      <WorkflowRecorderModal
        isOpen={true}
        onClose={handleClose}
        onPublished={handlePublished}
      />
    );

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('startRecording')).toBeInTheDocument();

    // 1. Click Start Recording
    fireEvent.click(screen.getByText('startRecording'));
    await waitFor(() => {
      expect(screen.getByText('recordingActive')).toBeInTheDocument();
    });

    // 2. Click Stop and Analyze
    fireEvent.click(screen.getByText('stopAndAnalyze'));
    await waitFor(() => {
      expect(screen.getByText('reviewStepsTitle')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Switch to Excel')).toBeInTheDocument();
    });

    // 3. Click Compile & Preview
    fireEvent.click(screen.getByText('compilePreview'));
    await waitFor(() => {
      expect(screen.getByText('previewTitle')).toBeInTheDocument();
    });

    // 4. Click Publish Skill
    fireEvent.click(screen.getByText('publishSkill'));
    await waitFor(() => {
      expect(screen.getByText('publishSuccessTitle')).toBeInTheDocument();
      expect(handlePublished).toHaveBeenCalledWith('Test Workflow Skill');
    });
  });
});
