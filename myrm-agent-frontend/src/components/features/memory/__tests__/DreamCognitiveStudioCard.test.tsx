/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::getDreamCognitiveOverview, listGrowthDiaries, getGrowthDiaryMarkdown, triggerCognitiveConsolidation
 * ../command-center/DreamCognitiveStudioCard::DreamCognitiveStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Dream Cognitive Consolidation Studio Card (Item 125 P1):
 * 1. Default render of header, HUD metrics bar and Active Cubes count
 * 2. Growth diary timeline list and active diary detail inspection
 * 3. Toggling between Structured View and Markdown View
 * 4. Switching active diary and fetching markdown
 * 5. Triggering dream consolidation run and displaying execution report
 *
 * [POS]
 * Unit tests for Item 125.
 * Strict typing applied: No `any` types allowed. Single file < 250 lines.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DreamCognitiveStudioCard } from '../command-center/DreamCognitiveStudioCard';
import {
  FALLBACK_CONSOLIDATION_REPORT,
  FALLBACK_DREAM_OVERVIEW,
  FALLBACK_GROWTH_DIARIES,
} from '../command-center/dreamCognitiveFallbacks';

const {
  mockGetDreamCognitiveOverview,
  mockListGrowthDiaries,
  mockGetGrowthDiaryMarkdown,
  mockTriggerCognitiveConsolidation,
} = vi.hoisted(() => ({
  mockGetDreamCognitiveOverview: vi.fn(),
  mockListGrowthDiaries: vi.fn(),
  mockGetGrowthDiaryMarkdown: vi.fn(),
  mockTriggerCognitiveConsolidation: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    getDreamCognitiveOverview: mockGetDreamCognitiveOverview,
    listGrowthDiaries: mockListGrowthDiaries,
    getGrowthDiaryMarkdown: mockGetGrowthDiaryMarkdown,
    triggerCognitiveConsolidation: mockTriggerCognitiveConsolidation,
  };
});

describe('DreamCognitiveStudioCard (Item 125 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetDreamCognitiveOverview.mockResolvedValue(FALLBACK_DREAM_OVERVIEW);
    mockListGrowthDiaries.mockResolvedValue(FALLBACK_GROWTH_DIARIES);
    mockGetGrowthDiaryMarkdown.mockImplementation((diaryId: string) =>
      Promise.resolve(`# Growth Diary ${diaryId}\n\nMarkdown reflection view.`)
    );
    mockTriggerCognitiveConsolidation.mockResolvedValue(FALLBACK_CONSOLIDATION_REPORT);
  });

  it('renders studio header, telemetry HUD metrics, and initial diary entries', async () => {
    render(<DreamCognitiveStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', {
          name: /Dream Cognitive Consolidation & AI Mind Growth Diary Studio/i,
        })
      ).toBeInTheDocument();
    });

    // Check HUD telemetry metrics
    expect(screen.getByText('Growth Diaries')).toBeInTheDocument();
    expect(screen.getByText('Cognitive Actions')).toBeInTheDocument();
    expect(screen.getByText('Active Cubes')).toBeInTheDocument();
    expect(screen.getByText('Non-Blocking Active')).toBeInTheDocument();

    // Verify presence of seeded diaries
    expect(
      screen.getAllByText(/Cognitive Leap in Typing Rigor: Internalizing Concrete Schemas/i).length
    ).toBeGreaterThan(0);
  });

  it('inspects active diary detail and displays actions and reasoning', async () => {
    render(<DreamCognitiveStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByText(/Embodied Reflection Narrative/i)
      ).toBeInTheDocument();
    });

    // Verify presence of actions and hypothetical deduction
    expect(screen.getByText(/Crystallized Cognitive Actions/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Hypothetical Query:/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Reasoning Gain:/i).length).toBeGreaterThan(0);
  });

  it('toggles between Structured View and Markdown View', async () => {
    render(<DreamCognitiveStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /^Markdown View$/i })
      ).toBeInTheDocument();
    });

    // Click Markdown View
    const mdBtn = screen.getByRole('button', { name: /^Markdown View$/i });
    fireEvent.click(mdBtn);

    await waitFor(() => {
      expect(mockGetGrowthDiaryMarkdown).toHaveBeenCalled();
      expect(screen.getByText(/Whitebox Markdown View/i)).toBeInTheDocument();
    });

    // Switch back to Structured View
    const structBtn = screen.getByRole('button', { name: /^Structured View$/i });
    fireEvent.click(structBtn);
    expect(screen.getByText(/Embodied Reflection Narrative/i)).toBeInTheDocument();
  });

  it('switches active diary and loads markdown', async () => {
    render(<DreamCognitiveStudioCard />);

    await waitFor(() => {
      expect(
        screen.getAllByText(/Mind Evolution: Multi-Agent Isolation and Zero Cross-Talk Governance/i).length
      ).toBeGreaterThan(0);
    });

    const secondDiaryBtns = screen.getAllByText(
      /Mind Evolution: Multi-Agent Isolation and Zero Cross-Talk Governance/i
    );
    fireEvent.click(secondDiaryBtns[0]);

    await waitFor(() => {
      expect(mockGetGrowthDiaryMarkdown).toHaveBeenCalledWith('diary-growth-002');
    });
  });

  it('triggers dream consolidation run and displays execution report', async () => {
    render(<DreamCognitiveStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Trigger Dream Consolidation/i })
      ).toBeInTheDocument();
    });

    const triggerBtn = screen.getByRole('button', { name: /Trigger Dream Consolidation/i });
    fireEvent.click(triggerBtn);

    await waitFor(() => {
      expect(mockTriggerCognitiveConsolidation).toHaveBeenCalled();
      expect(screen.getByText(/Consolidation Execution Report/i)).toBeInTheDocument();
      expect(screen.getByText('Facts Processed')).toBeInTheDocument();
      expect(screen.getByText('Clusters Formed')).toBeInTheDocument();
      expect(screen.getByText('Actions Mutated')).toBeInTheDocument();
    });
  });
});
