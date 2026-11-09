import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Message, ProgressItem } from '@/store/chat/types';
import { AssistantRunOutputs } from '../AssistantRunOutputs';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

type Props = Record<string, unknown>;

vi.mock('@/components/features/chat-window/ExecutionPhaseStepper', () => ({
  ExecutionPhaseStepper: (props: Props) => (
    <div
      data-testid="phase-stepper"
      data-loading={String(props.loading)}
      data-approval={String(props.isApprovalPending)}
    />
  ),
}));
vi.mock('@/components/features/chat-window/EvidenceStageHUD', () => ({
  EvidenceStageHUD: () => <div data-testid="evidence-hud" />,
}));
vi.mock('@/components/features/message-box/progress-steps/ProgressSteps', () => ({
  default: (props: { steps: unknown[] }) => <div data-testid="progress-steps" data-count={props.steps.length} />,
}));
vi.mock('@/components/features/message-box/SkillManageUndoHintCard', () => ({
  SkillManageUndoHintCard: () => <div data-testid="undo-hint" />,
}));
vi.mock('@/components/features/message-box/ConsensusThinkingPanel', () => ({
  default: (props: Props) => <div data-testid="consensus" data-streaming={String(props.isStreaming)} />,
}));
vi.mock('@/components/features/chat-window/approval/VisualApprovalInlineSection', () => ({
  default: (props: Props) => <div data-testid="visual-approval" data-chat={String(props.chatId)} />,
}));
vi.mock('@/components/features/chat-window/CouncilResultCard', () => ({
  CouncilResultCard: () => <div data-testid="council" />,
}));
vi.mock('@/components/features/artifacts/ArtifactsDisplay', () => ({ default: () => <div data-testid="artifacts" /> }));
vi.mock('@/components/features/artifacts/ArtifactErrorBoundary', () => ({
  default: (props: { children: React.ReactNode; fallbackMessage: string }) => (
    <div data-testid="mcp-boundary" data-fallback={props.fallbackMessage}>
      {props.children}
    </div>
  ),
}));
vi.mock('@/components/features/message-box/McpAppSection', () => ({
  McpAppSection: () => <div data-testid="mcp-app" />,
}));
vi.mock('@/components/features/message-box/ToolImageGallery', () => ({
  default: () => <div data-testid="tool-images" />,
}));
vi.mock('@/components/features/message-box/SessionRecordingCard', () => ({
  default: (props: Props) => <div data-testid="recording" data-file={String(props.filename)} />,
}));
vi.mock('@/components/features/message-box/TtsAudioCard', () => ({
  default: (props: Props) => <div data-testid="tts" data-url={String(props.url)} />,
}));
vi.mock('@/components/features/message-box/CronJobSystemCard', () => ({
  CronJobSystemCard: () => <div data-testid="cron" />,
}));
vi.mock('@/components/features/message-box/KanbanTaskCreatedCard', () => ({
  KanbanTaskCreatedCard: (props: { result: { task_id: string } }) => (
    <div data-testid="kanban" data-task={props.result.task_id} />
  ),
}));
vi.mock('@/components/features/task-card', () => ({
  ImageTaskCard: (props: Props) => <div data-testid="image-task" data-task={String(props.task_id)} />,
  VideoTaskCard: (props: Props) => <div data-testid="video-task" data-task={String(props.task_id)} />,
}));

function message(extra: Partial<Message> = {}): Message {
  return {
    messageId: 'a1',
    chatId: 'chat-1',
    role: 'assistant',
    content: 'answer',
    createdAt: new Date('2026-11-09T00:00:00.000Z'),
    ...extra,
  };
}

function renderOutputs(extra: Partial<Message> = {}, props: Partial<Parameters<typeof AssistantRunOutputs>[0]> = {}) {
  return render(
    <div data-testid="host">
      <AssistantRunOutputs
        message={message(extra)}
        loading={false}
        isLast={false}
        chatId="chat-1"
        approvalPending={false}
        taskResponse={null}
        ttsAudioResponse={null}
        {...props}
      />
    </div>,
  );
}

const SKILL_UNDO_STEP: ProgressItem = {
  step_key: 'skill_manage',
  tool_name: 'skill_manage_tool',
  skill_mutation_batch_id: 'batch-1',
};

describe('AssistantRunOutputs', () => {
  it('adds no wrapper: its blocks sit directly in the column of the bubble', () => {
    renderOutputs();
    const host = screen.getByTestId('host');

    expect(host.firstElementChild?.className).toBe('space-y-1.5');
    expect(screen.getByTestId('visual-approval').parentElement).toBe(host);
  });

  it('shows the analysis chip with its backend', () => {
    renderOutputs({ mediaAnalysisStatus: 'analyzing_image', visionBackend: 'vlm' });

    expect(screen.getByText('analyzing_image')).toBeTruthy();
    expect(screen.getByText('visionBackend.vlm')).toBeTruthy();
  });

  it('shows the phase stepper for a phase or for the latest streaming answer, and passes the approval flag', () => {
    renderOutputs({}, { loading: true, isLast: true, approvalPending: true });

    const stepper = screen.getByTestId('phase-stepper');
    expect(stepper.getAttribute('data-loading')).toBe('true');
    expect(stepper.getAttribute('data-approval')).toBe('true');
  });

  it('shows no phase stepper for a finished answer without a phase', () => {
    renderOutputs();

    expect(screen.queryByTestId('phase-stepper')).toBeNull();
  });

  it('keeps an earlier answer out of the streaming state of the stepper', () => {
    const phased = { phaseExecution: { phase: 'plan' } as unknown as Message['phaseExecution'] };
    const { unmount } = renderOutputs({}, { loading: true });
    expect(screen.queryByTestId('phase-stepper')).toBeNull();
    unmount();

    renderOutputs(phased, { loading: true });
    expect(screen.getByTestId('phase-stepper').getAttribute('data-loading')).toBe('false');
  });

  it('lists the steps of the message, or the copy in its metadata', () => {
    renderOutputs({ progressSteps: [], metadata: { progressSteps: [{ step_key: 'a' }, { step_key: 'b' }] } });

    expect(screen.getByTestId('progress-steps').getAttribute('data-count')).toBe('2');
    expect(screen.getByTestId('evidence-hud')).toBeTruthy();
  });

  it('offers the undo hint once the answer is done, not while it streams', () => {
    const { unmount } = renderOutputs({ progressSteps: [SKILL_UNDO_STEP] });
    expect(screen.getByTestId('undo-hint')).toBeTruthy();
    unmount();

    renderOutputs({ progressSteps: [SKILL_UNDO_STEP] }, { loading: true, isLast: true });
    expect(screen.queryByTestId('undo-hint')).toBeNull();
  });

  it.each([
    ['has no text yet', '', 'true'],
    ['has started to answer', 'first words', 'false'],
  ])('marks the consensus panel streaming only while the latest answer %s', (_label, content, expected) => {
    renderOutputs(
      { consensusRefs: [{ model: 'm1', success: true, elapsed: 1 }], content },
      { loading: true, isLast: true },
    );

    expect(screen.getByTestId('consensus').getAttribute('data-streaming')).toBe(expected);
  });

  it('marks the consensus panel as not streaming for an earlier answer', () => {
    renderOutputs({ consensusRefs: [{ model: 'm1', success: true, elapsed: 1 }], content: '' }, { loading: true });

    expect(screen.getByTestId('consensus').getAttribute('data-streaming')).toBe('false');
  });

  it('hands the chat to the approval section, or null without one', () => {
    renderOutputs({}, { chatId: undefined });

    expect(screen.getByTestId('visual-approval').getAttribute('data-chat')).toBe('null');
  });

  it('shows image and video task cards for a task reply', () => {
    const { unmount } = renderOutputs({}, { taskResponse: { task_id: 't1' } });
    expect(screen.getByTestId('image-task').getAttribute('data-task')).toBe('t1');
    unmount();

    renderOutputs({}, { taskResponse: { task_id: 't2', task_type: 'video_generate' } });
    expect(screen.getByTestId('video-task').getAttribute('data-task')).toBe('t2');
    expect(screen.queryByTestId('image-task')).toBeNull();
  });

  it('shows the council result and the generated artifacts when the message has them', () => {
    renderOutputs({
      councilResult: { verdict: 'ok' } as unknown as Message['councilResult'],
      artifacts: [{ id: 'art-1' }] as unknown as Message['artifacts'],
    });

    expect(screen.getByTestId('council')).toBeTruthy();
    expect(screen.getByTestId('artifacts')).toBeTruthy();
  });

  it('shows neither without a council result or artifacts', () => {
    renderOutputs({ artifacts: [] });

    expect(screen.queryByTestId('council')).toBeNull();
    expect(screen.queryByTestId('artifacts')).toBeNull();
  });

  it('plays a text-to-speech reply in place', () => {
    renderOutputs({}, { ttsAudioResponse: { audio_url: '/a.mp3' } });

    expect(screen.getByTestId('tts').getAttribute('data-url')).toBe('/a.mp3');
  });

  it('shows the cards of the attachments it recognises and ignores malformed ones', () => {
    renderOutputs({
      toolImages: [{ url: '/i.png' }] as unknown as Message['toolImages'],
      mcpApps: [{ id: 'app' }] as unknown as Message['mcpApps'],
      sessionRecording: { filename: 'r.webm', preview_url: '/r.webm', content_type: 'video/webm' },
      metadata: { cron_job_result: { job_id: 'j1' } },
    });

    expect(screen.getByTestId('tool-images')).toBeTruthy();
    expect(screen.getByTestId('mcp-boundary').getAttribute('data-fallback')).toBe('mcpAppRenderFailed');
    expect(screen.getByTestId('mcp-app')).toBeTruthy();
    expect(screen.getByTestId('recording').getAttribute('data-file')).toBe('r.webm');
    expect(screen.getByTestId('cron')).toBeTruthy();
  });

  it('skips a recording without a preview and attachments that are not lists', () => {
    renderOutputs({
      toolImages: 'oops' as unknown as Message['toolImages'],
      mcpApps: {} as unknown as Message['mcpApps'],
      sessionRecording: { filename: 'r.webm' } as unknown as Message['sessionRecording'],
    });

    expect(screen.queryByTestId('tool-images')).toBeNull();
    expect(screen.queryByTestId('mcp-boundary')).toBeNull();
    expect(screen.queryByTestId('recording')).toBeNull();
  });

  it('shows a kanban card per complete task, and none without a chat', () => {
    const task = { task_id: 'k1', title: 'Task', board_id: 'b1' };
    const metadata = { kanban_tasks_created: [task, { task_id: 'broken' }, { ...task, task_id: 'k2' }] };
    const { unmount } = renderOutputs({ metadata });
    expect(screen.getAllByTestId('kanban').map((card) => card.getAttribute('data-task'))).toEqual(['k1', 'k2']);
    unmount();

    renderOutputs({ metadata }, { chatId: undefined });
    expect(screen.queryByTestId('kanban')).toBeNull();
  });
});
