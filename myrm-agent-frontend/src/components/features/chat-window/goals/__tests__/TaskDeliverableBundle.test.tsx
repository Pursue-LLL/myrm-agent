'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { GoalState } from '../goalStatusTypes';

const stableT = (key: string, params?: { count?: number; defaultMessage?: string }) => {
  const map: Record<string, string> = {
    deliverableBundle: 'Task Deliverables',
    bundleDownloadAll: 'Download All',
    bundleDownloading: 'Downloading…',
    bundleDownloadFailed: 'Failed to download deliverables',
    bundleCategoryAll: 'All',
    bundleCategoryStrategy: 'Strategy & Overview',
    bundleCategoryCopywriting: 'Copywriting & Content',
    bundleCategoryVisual: 'Visual & Media',
    bundleCategoryDataSheet: 'Data & Sheets',
    bundleCategoryFactCheck: 'Fact Check & Audit',
    bundleCategorySchedule: 'Schedule & Plans',
    bundleCategoryCode: 'Code & Scripts',
    bundleCategoryOther: 'Other Assets',
  };
  if (map[key]) return map[key];
  if (params?.defaultMessage) return params.defaultMessage;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const mockOpenArtifact = vi.fn();
vi.mock('@/store/useArtifactPortalStore', () => ({
  default: (selector: (s: { openArtifact: typeof mockOpenArtifact }) => unknown) =>
    selector({ openArtifact: mockOpenArtifact }),
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn().mockResolvedValue({
    ok: true,
    blob: vi.fn().mockResolvedValue(new Blob(['dummy zip content'], { type: 'application/zip' })),
  }),
  getStorageUrl: (path: string) => `http://localhost:3000${path}`,
}));

vi.mock('@/components/features/artifacts/artifactUtils', () => ({
  getArtifactIcon: () => {
    const Icon = ({ className }: { className?: string }) => <svg data-testid="artifact-icon" className={className} />;
    return Icon;
  },
}));

import { TaskDeliverableBundle } from '../TaskDeliverableBundle';

const makeGoal = (overrides: Partial<GoalState> = {}): GoalState => ({
  goalId: 'goal-1',
  objective: 'Generate quarterly report and social campaign',
  status: 'complete',
  tokensUsed: 50000,
  timeUsedSeconds: 300,
  deliverables: [
    { id: 'art-1', filename: 'campaign_strategy.md' },
    { id: 'art-2', filename: 'xhs_article.md' },
    { id: 'art-3', filename: 'banner.png' },
    { id: 'art-4', filename: 'financial_data.xlsx' },
    { id: 'art-5', filename: 'fact_check_sheet.md' },
  ],
  ...overrides,
});

describe('TaskDeliverableBundle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.URL.createObjectURL = vi.fn().mockReturnValue('blob:dummy');
    global.URL.revokeObjectURL = vi.fn();
  });

  it('renders deliverable list and category filter tabs when goal is complete with 2+ items', () => {
    render(<TaskDeliverableBundle goal={makeGoal()} chatId="chat-1" />);
    expect(screen.getByText('Task Deliverables')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();

    // Verify all files rendered
    expect(screen.getByText('campaign_strategy.md')).toBeInTheDocument();
    expect(screen.getByText('xhs_article.md')).toBeInTheDocument();
    expect(screen.getByText('banner.png')).toBeInTheDocument();
    expect(screen.getByText('financial_data.xlsx')).toBeInTheDocument();
    expect(screen.getByText('fact_check_sheet.md')).toBeInTheDocument();
  });

  it('filters items when category tab is clicked', () => {
    render(<TaskDeliverableBundle goal={makeGoal()} chatId="chat-1" />);
    
    // Click on Strategy tab (supports i18n mock and default message)
    const strategyTab = screen.getByText(/Strategy & Overview|策略与方案/);
    fireEvent.click(strategyTab);

    // Strategy item is visible, others are filtered out
    expect(screen.getByText('campaign_strategy.md')).toBeInTheDocument();
    expect(screen.queryByText('xhs_article.md')).not.toBeInTheDocument();
    expect(screen.queryByText('banner.png')).not.toBeInTheDocument();
  });

  it('supports selecting items and exporting selected subset', async () => {
    render(<TaskDeliverableBundle goal={makeGoal()} chatId="chat-1" />);
    
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes.length).toBe(5);

    // Select first two items
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);

    // Button for selected export appears
    const exportSelectedBtn = screen.getByText(/导出选中 \(2\)/);
    expect(exportSelectedBtn).toBeInTheDocument();

    fireEvent.click(exportSelectedBtn);
  });

  it('returns null when deliverables is empty or has < 2 items', () => {
    const { container: c1 } = render(<TaskDeliverableBundle goal={makeGoal({ deliverables: [] })} chatId="chat-1" />);
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <TaskDeliverableBundle goal={makeGoal({ deliverables: [{ id: '1', filename: 'a.txt' }] })} chatId="chat-1" />,
    );
    expect(c2.firstChild).toBeNull();
  });

  it('returns null when goal is not complete', () => {
    const { container } = render(<TaskDeliverableBundle goal={makeGoal({ status: 'active' })} chatId="chat-1" />);
    expect(container.firstChild).toBeNull();
  });

  it('opens artifact portal on item click', () => {
    render(<TaskDeliverableBundle goal={makeGoal()} chatId="chat-1" />);
    fireEvent.click(screen.getByText('campaign_strategy.md'));
    expect(mockOpenArtifact).toHaveBeenCalledTimes(1);
    expect(mockOpenArtifact).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'art-1',
        filename: 'campaign_strategy.md',
        type: 'document',
      }),
    );
  });
});
