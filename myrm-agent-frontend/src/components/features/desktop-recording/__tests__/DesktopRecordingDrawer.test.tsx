import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { DesktopRecordingDrawer } from '../DesktopRecordingDrawer';
import { useDesktopRecordingStore } from '@/store/useDesktopRecordingStore';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params && 'count' in params) {
    return `${key} (${params.count})`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

describe('DesktopRecordingDrawer Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDesktopRecordingStore.setState({
      isOpen: true,
      status: 'idle',
      sessionId: null,
      appScope: 'all',
      steps: [],
      draft: null,
      publishedSkillId: null,
      error: null,
    });
  });

  it('renders correctly when open with initial idle state', () => {
    render(<DesktopRecordingDrawer />);
    expect(screen.getByRole('dialog', { name: 'drawerTitle' })).toBeInTheDocument();
    expect(screen.getByText('drawerTitle')).toBeInTheDocument();
    expect(screen.getByText('status_idle')).toBeInTheDocument();
    expect(screen.getByText('btnStart')).toBeInTheDocument();
  });

  it('renders recording state with stop button', () => {
    useDesktopRecordingStore.setState({
      isOpen: true,
      status: 'recording',
      sessionId: 'rec_123',
    });

    render(<DesktopRecordingDrawer />);
    expect(screen.getByText('btnStop')).toBeInTheDocument();
    expect(screen.getByText('status_recording')).toBeInTheDocument();
  });

  it('displays recorded steps and permits deletion', () => {
    useDesktopRecordingStore.setState({
      isOpen: true,
      status: 'stopped',
      sessionId: 'rec_123',
      steps: [
        {
          seq: 1,
          action: 'click',
          app_name: 'Excel',
          window_title: 'Sheet1',
          element_title: 'Save Button',
          is_password: false,
        },
      ],
    });

    render(<DesktopRecordingDrawer />);
    expect(screen.getByText('click "Save Button"')).toBeInTheDocument();
    expect(screen.getByText('[Excel]')).toBeInTheDocument();
  });

  it('displays synthesized draft and tool lifting badge when draft ready', () => {
    useDesktopRecordingStore.setState({
      isOpen: true,
      status: 'draft_ready',
      sessionId: 'rec_123',
      draft: {
        skill_name: 'excel_export_workflow',
        description: 'Auto export spreadsheet',
        triggers: ['run excel_export_workflow'],
        parameters: [{ name: 'input_file', type: 'string', description: 'Input file' }],
        steps: [],
        markdown_content: '# excel_export_workflow\n\nWorkflow steps...',
        tool_lifting_applied: true,
        created_at: Date.now(),
      },
    });

    render(<DesktopRecordingDrawer />);
    expect(screen.getByText('draftTitle')).toBeInTheDocument();
    expect(screen.getByText('toolLiftingActive')).toBeInTheDocument();
    expect(screen.getByText('{{input_file}}')).toBeInTheDocument();
    expect(screen.getByText('btnPublish')).toBeInTheDocument();
  });
});
