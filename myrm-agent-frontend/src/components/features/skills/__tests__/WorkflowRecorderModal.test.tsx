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
  startDesktopRecording: vi.fn().mockResolvedValue({
    session_id: 'rec-123',
    status: 'recording',
    started_at: 1000,
    capture_active: true,
    capture_error: null,
  }),
  stopDesktopRecording: vi
    .fn()
    .mockResolvedValue({ session_id: 'rec-123', status: 'stopped', event_count: 2, duration_seconds: 5 }),
  recordDesktopEvent: vi.fn().mockResolvedValue({ status: 'ok', recorded_count: 1 }),
  // Live session polling; the capture state is asserted through dialog copy, not the count.
  getDesktopRecordingSession: vi.fn().mockResolvedValue({
    session_id: 'rec-123',
    status: 'recording',
    events_count: 2,
    capture_active: true,
    capture_error: null,
  }),
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

    render(<WorkflowRecorderModal isOpen={true} onClose={handleClose} onPublished={handlePublished} />);

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

    // 3. Test Add Step
    const addBtn = screen.getByText('addStep');
    fireEvent.click(addBtn);
    expect(screen.getByDisplayValue('New Custom Action')).toBeInTheDocument();

    // 4. Click Compile & Preview
    fireEvent.click(screen.getByText('compilePreview'));
    await waitFor(() => {
      expect(screen.getByText('previewTitle')).toBeInTheDocument();
    });

    // 5. Click Publish Skill
    fireEvent.click(screen.getByText('publishSkill'));
    await waitFor(() => {
      expect(screen.getByText('publishSuccessTitle')).toBeInTheDocument();
      expect(handlePublished).toHaveBeenCalledWith('Test Workflow Skill');
    });
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(<WorkflowRecorderModal isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('surfaces a capture that stops mid-recording', async () => {
    const sessionPoll = vi.mocked(skillService.getDesktopRecordingSession);
    // Capture was running at start, then the platform reported it stopped (e.g. the user
    // revoked Accessibility access) — the dialog must switch back to manual step entry.
    sessionPoll.mockResolvedValue({
      session_id: 'rec-123',
      status: 'recording',
      events_count: 5,
      capture_active: false,
      capture_error: 'desktop_capture_permission_required',
    });

    render(<WorkflowRecorderModal isOpen={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText('startRecording'));

    await waitFor(() => {
      expect(screen.getByText('manualRecordingActive')).toBeInTheDocument();
    });
    // The guidance must be actionable, not a generic notice.
    expect(screen.getByText('capturePermissionNotice')).toBeInTheDocument();
  });

  it('stops the server-side capture when closed mid-recording', async () => {
    const stopMock = vi.mocked(skillService.stopDesktopRecording);
    stopMock.mockClear();

    render(<WorkflowRecorderModal isOpen={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByText('startRecording'));
    await waitFor(() => {
      expect(screen.getByText('recordingActive')).toBeInTheDocument();
    });

    // Dismissing the dialog must not leave the platform capture loop running.
    fireEvent.click(screen.getByLabelText('Close'));

    await waitFor(() => {
      expect(stopMock).toHaveBeenCalled();
    });
  });

  it('does not call stop when closing without an active recording', async () => {
    const stopMock = vi.mocked(skillService.stopDesktopRecording);
    stopMock.mockClear();

    render(<WorkflowRecorderModal isOpen={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByLabelText('Close'));

    expect(stopMock).not.toHaveBeenCalled();
  });

  it('falls back to honest manual step entry when platform capture is unavailable', async () => {
    const startMock = vi.mocked(skillService.startDesktopRecording);
    const sessionPoll = vi.mocked(skillService.getDesktopRecordingSession);
    // A platform without AX capture reports capture_active=false, so the modal must disclose
    // that steps are entered manually instead of implying an automatic recording is running.
    startMock.mockResolvedValueOnce({
      session_id: 'rec-manual',
      status: 'recording',
      started_at: 1000,
      capture_active: false,
      capture_error: 'desktop_capture_unavailable: no AX backend',
    });
    sessionPoll.mockResolvedValue({
      session_id: 'rec-manual',
      status: 'recording',
      events_count: 0,
      capture_active: false,
      capture_error: 'desktop_capture_unavailable: no AX backend',
    });

    render(<WorkflowRecorderModal isOpen={true} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText('startRecording'));

    await waitFor(() => {
      expect(screen.getByText('manualRecordingActive')).toBeInTheDocument();
    });
    // Platform-level unavailability is reported as unsupported, distinct from a permission ask.
    expect(screen.getByText('captureUnsupportedNotice')).toBeInTheDocument();
    // The automatic-capture copy must not be shown while capture is unavailable.
    expect(screen.queryByText('captureHint')).not.toBeInTheDocument();
  });
});
