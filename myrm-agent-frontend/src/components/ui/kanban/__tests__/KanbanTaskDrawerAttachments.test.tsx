import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { KanbanTask, TaskStatus, AttachmentInfo } from '@/services/kanban';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/hooks/useAgentName', () => ({
  useAgentName: () => null,
}));

const mockAgentStore = { agents: [] as never[], fetchAgents: vi.fn() };
vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (s: typeof mockAgentStore) => unknown) => selector(mockAgentStore),
  __esModule: true,
}));

vi.mock('@/services/kanban', () => ({
  listRuns: vi.fn().mockResolvedValue({ items: [] }),
  listEvents: vi.fn().mockResolvedValue({ items: [] }),
  listDependencies: vi.fn().mockResolvedValue({ items: [] }),
  listDependents: vi.fn().mockResolvedValue({ items: [] }),
  addComment: vi.fn(),
  addDependency: vi.fn(),
  removeDependency: vi.fn(),
  getTask: vi.fn(),
  moveTask: vi.fn(),
  promoteTask: vi.fn(),
  reclaimTask: vi.fn(),
  updateTask: vi.fn().mockResolvedValue({}),
  getTaskDiagnostics: vi.fn().mockResolvedValue({ diagnostics: [] }),
}));

vi.mock('@/lib/api', () => ({
  getApiUrl: (path: string) => `http://localhost:8080/api/v1${path}`,
}));

vi.mock('../KanbanDiagnosticsSection', () => ({
  default: () => <div data-testid="diagnostics" />,
}));

vi.mock('../KanbanEventTimeline', () => ({
  KanbanRunHistory: () => null,
  KanbanEventTimeline: () => null,
}));

vi.mock('../KanbanMarkdown', () => ({
  default: ({ children }: { children: string }) => <span>{children}</span>,
}));

function makeMockTask(overrides: Partial<KanbanTask> = {}): KanbanTask {
  return {
    task_id: 'task-att-1',
    board_id: 'board-1',
    title: 'Attachment Test Task',
    description: 'A task with attachments',
    status: 'ready' as TaskStatus,
    priority: 'normal',
    retry_count: 0,
    max_retries: 3,
    consecutive_failures: 0,
    result: '',
    error: '',
    metadata: {},
    extra_skill_ids: [],
    attachment_ids: [],
    attachments: [],
    dep_count: 0,
    children_total: 0,
    children_done: 0,
    comment_count: 0,
    created_at: '2026-05-29T00:00:00Z',
    updated_at: '2026-05-29T00:00:00Z',
    ...overrides,
  };
}

function makeAttachment(overrides: Partial<AttachmentInfo> = {}): AttachmentInfo {
  return {
    file_id: 'file-1',
    filename: 'test.png',
    content_type: 'image/png',
    url: '/api/v1/files/file-1/content',
    ...overrides,
  };
}

async function renderDrawer(task: KanbanTask) {
  const KanbanTaskDrawer = (await import('../KanbanTaskDrawer')).default;
  const onOpenChange = vi.fn();
  const onRefresh = vi.fn();
  const utils = render(
    <KanbanTaskDrawer task={task} allTasks={[task]} open={true} onOpenChange={onOpenChange} onRefresh={onRefresh} />,
  );
  await waitFor(
    () => {
      expect(screen.queryByText('attachments')).toBeTruthy();
    },
    { timeout: 3000 },
  );
  return { ...utils, onOpenChange, onRefresh };
}

describe('KanbanTaskDrawer Attachments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  it('shows empty state when no attachments', async () => {
    const task = makeMockTask({ attachment_ids: [], attachments: [] });
    await renderDrawer(task);
    await waitFor(() => {
      expect(screen.getByText('noAttachments')).toBeTruthy();
    });
  });

  it('shows image attachments as thumbnails', async () => {
    const att = makeAttachment({
      file_id: 'img-1',
      filename: 'photo.jpg',
      content_type: 'image/jpeg',
      url: '/api/v1/files/img-1/content',
    });
    const task = makeMockTask({
      attachment_ids: ['img-1'],
      attachments: [att],
    });
    await renderDrawer(task);
    await waitFor(() => {
      const img = screen.getByAltText('photo.jpg');
      expect(img).toBeTruthy();
      expect(img.getAttribute('src')).toBe('/api/v1/files/img-1/content');
    });
  });

  it('shows non-image attachments as file links', async () => {
    const att = makeAttachment({
      file_id: 'doc-1',
      filename: 'report.pdf',
      content_type: 'application/pdf',
      url: '/api/v1/files/doc-1/content',
    });
    const task = makeMockTask({
      attachment_ids: ['doc-1'],
      attachments: [att],
    });
    await renderDrawer(task);
    await waitFor(() => {
      expect(screen.getByText('report.pdf')).toBeTruthy();
    });
  });

  it('shows attachment count in header', async () => {
    const atts: AttachmentInfo[] = [
      makeAttachment({ file_id: 'f1', filename: 'a.png', content_type: 'image/png' }),
      makeAttachment({ file_id: 'f2', filename: 'b.pdf', content_type: 'application/pdf' }),
      makeAttachment({ file_id: 'f3', filename: 'c.csv', content_type: 'text/csv' }),
    ];
    const task = makeMockTask({
      attachment_ids: ['f1', 'f2', 'f3'],
      attachments: atts,
    });
    await renderDrawer(task);
    await waitFor(() => {
      expect(screen.getByText('(3)')).toBeTruthy();
    });
  });

  it('calls updateTask with new attachment_ids on file upload', async () => {
    const { updateTask } = await import('@/services/kanban');
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ file_id: 'new-file-1', filename: 'test.png', content_type: 'image/png' }),
    });

    const att = makeAttachment({ file_id: 'existing-1', filename: 'old.jpg', content_type: 'image/jpeg' });
    const task = makeMockTask({ attachment_ids: ['existing-1'], attachments: [att] });
    const { onRefresh } = await renderDrawer(task);

    await waitFor(() => {
      expect(screen.getByText('+ addAttachment')).toBeTruthy();
    });

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();

    const file = new File(['data'], 'test.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(updateTask).toHaveBeenCalledWith('task-att-1', {
        attachment_ids: ['existing-1', 'new-file-1'],
      });
      expect(onRefresh).toHaveBeenCalled();
    });
  });

  it('calls updateTask to remove attachment', async () => {
    const { updateTask } = await import('@/services/kanban');

    const atts: AttachmentInfo[] = [
      makeAttachment({ file_id: 'f1', filename: 'a.png', content_type: 'image/png' }),
      makeAttachment({ file_id: 'f2', filename: 'b.pdf', content_type: 'application/pdf' }),
    ];
    const task = makeMockTask({
      attachment_ids: ['f1', 'f2'],
      attachments: atts,
    });
    await renderDrawer(task);

    await waitFor(() => {
      const removeButtons = screen.getAllByTitle('removeAttachment');
      expect(removeButtons.length).toBe(2);
      fireEvent.click(removeButtons[0]);
    });

    await waitFor(() => {
      expect(updateTask).toHaveBeenCalledWith('task-att-1', {
        attachment_ids: ['f2'],
      });
    });
  });

  it('handles drag over state', async () => {
    const task = makeMockTask({ attachment_ids: [], attachments: [] });
    await renderDrawer(task);

    await waitFor(() => {
      expect(screen.getByText('noAttachments')).toBeTruthy();
    });

    const section = screen.getByText('noAttachments').closest('section')!;
    fireEvent.dragOver(section, { preventDefault: () => {} });

    await waitFor(() => {
      expect(screen.getByText('dropFilesHere')).toBeTruthy();
    });
  });

  it('handles drop to upload files', async () => {
    const { updateTask } = await import('@/services/kanban');
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ file_id: 'dropped-file', filename: 'dropped.png', content_type: 'image/png' }),
    });

    const task = makeMockTask({ attachment_ids: [], attachments: [] });
    const { onRefresh } = await renderDrawer(task);

    await waitFor(() => {
      expect(screen.getByText('noAttachments')).toBeTruthy();
    });

    const section = screen.getByText('noAttachments').closest('section')!;
    const file = new File(['data'], 'dropped.png', { type: 'image/png' });

    fireEvent.drop(section, {
      preventDefault: () => {},
      dataTransfer: { files: [file] },
    });

    await waitFor(() => {
      expect(updateTask).toHaveBeenCalledWith('task-att-1', {
        attachment_ids: ['dropped-file'],
      });
      expect(onRefresh).toHaveBeenCalled();
    });
  });
});
