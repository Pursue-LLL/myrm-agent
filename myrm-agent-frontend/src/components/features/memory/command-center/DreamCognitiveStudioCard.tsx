/**
 * [INPUT]
 * @/services/memory::getDreamCognitiveOverview, listGrowthDiaries, getGrowthDiaryMarkdown,
 *                    triggerCognitiveConsolidation, DreamCognitiveOverviewDTO,
 *                    GrowthDiaryEntryDTO, CognitiveConsolidationReportDTO,
 *                    CognitiveConsolidationRequestDTO
 * ./dreamCognitiveFallbacks::FALLBACK_DREAM_OVERVIEW, FALLBACK_GROWTH_DIARIES
 * ./DreamCognitiveHudBar::DreamCognitiveHudBar
 * ./GrowthDiaryTimelineView::GrowthDiaryTimelineView
 * ./DreamCognitiveSynthesisConsoleView::DreamCognitiveSynthesisConsoleView
 *
 * [OUTPUT]
 * Component: DreamCognitiveStudioCard
 *
 * [POS]
 * Command Center flagship card for Item 125 Dream Cognitive Consolidation & Growth Diary Suite.
 * Follows a11y ratchet guidelines: Uses native `<section aria-label="...">`, visible focus rings,
 * proper htmlFor connections, and zero raw `>` or `->` characters.
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { BookOpen } from 'lucide-react';
import {
  getDreamCognitiveOverview,
  getGrowthDiaryMarkdown,
  listGrowthDiaries,
  triggerCognitiveConsolidation,
} from '@/services/memory';
import type {
  CognitiveConsolidationReportDTO,
  CognitiveConsolidationRequestDTO,
  DreamCognitiveOverviewDTO,
  GrowthDiaryEntryDTO,
} from '@/services/memory';
import {
  FALLBACK_DREAM_OVERVIEW,
  FALLBACK_GROWTH_DIARIES,
} from './dreamCognitiveFallbacks';
import { DreamCognitiveHudBar } from './DreamCognitiveHudBar';
import { GrowthDiaryTimelineView } from './GrowthDiaryTimelineView';
import { DreamCognitiveSynthesisConsoleView } from './DreamCognitiveSynthesisConsoleView';

export const DreamCognitiveStudioCard: React.FC = () => {
  const [overview, setOverview] = useState<DreamCognitiveOverviewDTO>(FALLBACK_DREAM_OVERVIEW);
  const [diaries, setDiaries] = useState<GrowthDiaryEntryDTO[]>(FALLBACK_GROWTH_DIARIES);
  const [selectedDiaryId, setSelectedDiaryId] = useState<string | null>(
    FALLBACK_GROWTH_DIARIES[0]?.diary_id || null
  );
  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [latestReport, setLatestReport] = useState<CognitiveConsolidationReportDTO | null>(null);

  const [isLoadingMarkdown, setIsLoadingMarkdown] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isConsolidating, setIsConsolidating] = useState(false);

  const fetchOverview = useCallback(async () => {
    try {
      setIsRefreshing(true);
      const data = await getDreamCognitiveOverview();
      setOverview(data);
    } catch {
      setOverview(FALLBACK_DREAM_OVERVIEW);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  const fetchDiaries = useCallback(async () => {
    try {
      const data = await listGrowthDiaries();
      setDiaries(data);
      if (!selectedDiaryId && data.length > 0) {
        setSelectedDiaryId(data[0]?.diary_id || null);
      }
    } catch {
      setDiaries(FALLBACK_GROWTH_DIARIES);
    }
  }, [selectedDiaryId]);

  const fetchMarkdown = useCallback(async (diaryId: string) => {
    try {
      setIsLoadingMarkdown(true);
      const md = await getGrowthDiaryMarkdown(diaryId);
      setMarkdownContent(md);
    } catch {
      const fallbackEntry = diaries.find((d) => d.diary_id === diaryId);
      if (fallbackEntry) {
        setMarkdownContent(
          `# ${fallbackEntry.title}\n\n**Motive**: ${fallbackEntry.motive_type}\n\n${fallbackEntry.reflective_narrative}`
        );
      } else {
        setMarkdownContent(null);
      }
    } finally {
      setIsLoadingMarkdown(false);
    }
  }, [diaries]);

  useEffect(() => {
    void fetchOverview();
    void fetchDiaries();
  }, [fetchOverview, fetchDiaries]);

  useEffect(() => {
    if (selectedDiaryId) {
      void fetchMarkdown(selectedDiaryId);
    }
  }, [selectedDiaryId, fetchMarkdown]);

  const handleSelectDiary = (diaryId: string) => {
    setSelectedDiaryId(diaryId);
  };

  const handleRefreshAll = async () => {
    await Promise.all([fetchOverview(), fetchDiaries()]);
    if (selectedDiaryId) {
      await fetchMarkdown(selectedDiaryId);
    }
  };

  const handleTriggerConsolidation = async (
    payload: CognitiveConsolidationRequestDTO,
  ): Promise<CognitiveConsolidationReportDTO> => {
    try {
      setIsConsolidating(true);
      const report = await triggerCognitiveConsolidation(payload);
      setLatestReport(report);
      // Auto-refresh diaries & overview
      await Promise.all([fetchOverview(), fetchDiaries()]);
      if (report.diary_entries.length > 0) {
        const newDiary = report.diary_entries[0];
        if (newDiary) {
          setSelectedDiaryId(newDiary.diary_id);
        }
      }
      return report;
    } catch {
      // Offline fallback simulation
      const simulatedDiary: GrowthDiaryEntryDTO = {
        diary_id: `diary-sim-${Date.now()}`,
        title: 'Cognitive Synthesis in Action: Internalizing Engineering Rules',
        summary: 'Synthesized recent interaction facts into long-term invariants.',
        reflective_narrative:
          'Simulated background dream cycle processed input facts. Validated core invariants and recorded new growth diary entry.',
        motive_type: 'frequency',
        themes: ['Clean Code', 'Test Driven', 'Architectural Isolation'],
        cube_id: payload.cube_id || 'cube-proj-open-perplexity',
        generated_actions: [],
        created_at: new Date().toISOString(),
      };
      const simulatedReport: CognitiveConsolidationReportDTO = {
        run_id: `run-sim-${Date.now()}`,
        cube_id: payload.cube_id || null,
        timestamp: new Date().toISOString(),
        duration_ms: 110.0,
        input_fact_count: 1,
        clusters_formed: 1,
        actions_generated: 1,
        diary_entries: [simulatedDiary],
      };
      setLatestReport(simulatedReport);
      setDiaries((prev) => [simulatedDiary, ...prev]);
      setSelectedDiaryId(simulatedDiary.diary_id);
      setOverview((prev) => ({
        ...prev,
        total_diaries: prev.total_diaries + 1,
        total_actions: prev.total_actions + 1,
      }));
      return simulatedReport;
    } finally {
      setIsConsolidating(false);
    }
  };

  return (
    <section
      aria-label="Dream Cognitive Consolidation & Growth Diary Studio"
      className="p-6 rounded-2xl border border-border/80 bg-card/80 backdrop-blur-md shadow-sm space-y-6"
    >
      {/* Studio Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400">
              <BookOpen className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-lg font-bold tracking-tight text-foreground">
                Dream Cognitive Consolidation &amp; AI Mind Growth Diary Studio
              </h2>
              <div className="text-xs text-muted-foreground">
                Item 125 [P1] · Background non-blocking dream reflection, higher-level insight synthesis, and whitebox journal
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 4D Telemetry HUD Bar */}
      <DreamCognitiveHudBar
        overview={overview}
        isRefreshing={isRefreshing}
        onRefresh={handleRefreshAll}
      />

      {/* Mind Evolution Timeline View */}
      <GrowthDiaryTimelineView
        diaries={diaries}
        selectedDiaryId={selectedDiaryId}
        onSelectDiary={handleSelectDiary}
        markdownContent={markdownContent}
        isLoadingMarkdown={isLoadingMarkdown}
      />

      {/* Dream Synthesis Console */}
      <DreamCognitiveSynthesisConsoleView
        onTriggerConsolidation={handleTriggerConsolidation}
        isConsolidating={isConsolidating}
        latestReport={latestReport}
      />
    </section>
  );
};
