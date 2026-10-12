/**
 * [INPUT]
 * @/services/memory::GrowthDiaryEntryDTO, DreamMotiveTypeEnum
 * onSelectDiary: (diaryId: string) => void, selectedDiaryId?: string | null
 * markdownContent?: string | null, isLoadingMarkdown: boolean
 *
 * [OUTPUT]
 * Component: GrowthDiaryTimelineView
 *
 * [POS]
 * Whitebox timeline journal presentation for Item 125 Dream Cognitive Consolidation & Growth Diary Suite.
 * Follows a11y ratchet guidelines: Uses native `<section aria-label="...">`, visible focus rings,
 * native button triggers, and zero raw `>` or `->` characters.
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { BookOpen, Tag, Calendar, Sparkles, FileText, ChevronRight, Eye } from 'lucide-react';
import type { DreamMotiveTypeEnum, GrowthDiaryEntryDTO } from '@/services/memory';

interface GrowthDiaryTimelineViewProps {
  diaries: GrowthDiaryEntryDTO[];
  selectedDiaryId: string | null;
  onSelectDiary: (diaryId: string) => void;
  markdownContent: string | null;
  isLoadingMarkdown: boolean;
}

export const GrowthDiaryTimelineView: React.FC<GrowthDiaryTimelineViewProps> = ({
  diaries,
  selectedDiaryId,
  onSelectDiary,
  markdownContent,
  isLoadingMarkdown,
}) => {
  const [viewMode, setViewMode] = useState<'structured' | 'markdown'>('structured');

  const activeDiary =
    diaries.find((d) => d.diary_id === selectedDiaryId) || diaries[0] || null;

  const getMotiveBadge = (motive: DreamMotiveTypeEnum) => {
    switch (motive) {
      case 'frequency':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
            Frequency Synthesis
          </span>
        );
      case 'conflict':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
            Conflict Resolution
          </span>
        );
      case 'feedback':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            Feedback Internalization
          </span>
        );
      case 'fragmentation':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            Fragmentation De-dup
          </span>
        );
      case 'newness':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
            Newness Ingestion
          </span>
        );
    }
  };

  return (
    <section
      aria-label="Agent Growth Diary Timeline"
      className="p-5 rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm space-y-4"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/40 pb-3">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" aria-hidden="true" />
            AI Mind Evolution &amp; Growth Diary Timeline
          </h3>
          <p className="text-xs text-muted-foreground">
            Whitebox transparent self-reflection entries synthesized during background dream cycles.
          </p>
        </div>

        {/* View mode toggle */}
        <div className="flex items-center gap-2">
          <div className="flex items-center p-0.5 rounded-lg border border-border/60 bg-muted/30 text-xs">
            <button
              type="button"
              onClick={() => setViewMode('structured')}
              className={`px-2.5 py-1 rounded-md font-medium transition-all focus:ring-2 focus:ring-primary focus:outline-none ${
                viewMode === 'structured'
                  ? 'bg-background text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Structured View
            </button>
            <button
              type="button"
              onClick={() => setViewMode('markdown')}
              className={`px-2.5 py-1 rounded-md font-medium transition-all focus:ring-2 focus:ring-primary focus:outline-none ${
                viewMode === 'markdown'
                  ? 'bg-background text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Markdown View
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Split: Left Diary Cards List, Right Active Diary Detail */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
        {/* Diary entries list */}
        <div className="md:col-span-5 space-y-2.5 max-h-[420px] overflow-y-auto pr-1">
          {diaries.map((diary) => {
            const isSelected = activeDiary?.diary_id === diary.diary_id;
            return (
              <button
                key={diary.diary_id}
                type="button"
                onClick={() => onSelectDiary(diary.diary_id)}
                className={`w-full p-3 rounded-lg border text-left transition-all cursor-pointer focus:ring-2 focus:ring-primary focus:outline-none ${
                  isSelected
                    ? 'border-primary bg-primary/5 shadow-xs'
                    : 'border-border/60 bg-card hover:border-border hover:bg-muted/30'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="text-xs font-bold text-foreground line-clamp-1">{diary.title}</div>
                  {getMotiveBadge(diary.motive_type)}
                </div>
                <p className="text-[11px] text-muted-foreground line-clamp-2 mb-2">
                  {diary.summary}
                </p>
                <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                  <span className="flex items-center gap-1 font-mono">
                    <Calendar className="w-3 h-3" aria-hidden="true" />
                    {new Date(diary.created_at).toLocaleDateString()}
                  </span>
                  <div className="flex items-center gap-1">
                    {diary.cube_id && (
                      <span className="font-mono text-primary/80">[{diary.cube_id}]</span>
                    )}
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" aria-hidden="true" />
                  </div>
                </div>
              </button>
            );
          })}
          {diaries.length === 0 && (
            <div className="p-8 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
              No growth diaries recorded yet. Trigger a dream consolidation cycle below.
            </div>
          )}
        </div>

        {/* Selected Diary Detail View */}
        <div className="md:col-span-7 p-4 rounded-lg border border-border/60 bg-muted/10 space-y-4 max-h-[420px] overflow-y-auto pr-1">
          {activeDiary ? (
            viewMode === 'structured' ? (
              <div className="space-y-4">
                {/* Header info */}
                <div className="border-b border-border/40 pb-3 space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <h4 className="text-sm font-bold text-foreground">{activeDiary.title}</h4>
                    {getMotiveBadge(activeDiary.motive_type)}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="font-mono">{activeDiary.diary_id}</span>
                    <span>&bull;</span>
                    <span>{new Date(activeDiary.created_at).toLocaleString()}</span>
                    {activeDiary.cube_id && (
                      <>
                        <span>&bull;</span>
                        <span className="font-mono text-primary font-medium">Cube: {activeDiary.cube_id}</span>
                      </>
                    )}
                  </div>
                  {/* Themes badges */}
                  {activeDiary.themes.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {activeDiary.themes.map((theme) => (
                        <span
                          key={theme}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-secondary text-secondary-foreground"
                        >
                          <Tag className="w-2.5 h-2.5" aria-hidden="true" />
                          {theme}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Reflective Narrative */}
                <div className="space-y-1.5">
                  <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Eye className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
                    Embodied Reflection Narrative
                  </div>
                  <div className="p-3 rounded-md bg-card border border-border/40 text-xs text-foreground leading-relaxed">
                    {activeDiary.reflective_narrative}
                  </div>
                </div>

                {/* Generated Cognitive Actions */}
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-purple-500" aria-hidden="true" />
                    Crystallized Cognitive Actions ({activeDiary.generated_actions.length})
                  </div>
                  <div className="space-y-2">
                    {activeDiary.generated_actions.map((act) => (
                      <div
                        key={act.action_id}
                        className="p-3 rounded-md bg-card border border-border/40 space-y-1.5 text-xs"
                      >
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="font-mono font-bold text-primary">
                            [{act.action_type.toUpperCase()}] &rarr; {act.target_type}
                          </span>
                          <span className="text-muted-foreground font-mono">
                            Conf: {(act.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="text-foreground font-medium">{act.payload_statement}</div>
                        {/* Deductive Reasoning */}
                        <div className="p-2 rounded bg-muted/40 text-[11px] text-muted-foreground space-y-0.5">
                          <div>
                            <span className="font-semibold text-foreground">Hypothetical Query: </span>
                            {act.deduction.hypothetical_query}
                          </div>
                          <div>
                            <span className="font-semibold text-foreground">Reasoning Gain: </span>
                            {act.deduction.improved_response_reasoning}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              /* Markdown Raw View */
              <div className="space-y-2">
                <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
                  Whitebox Markdown View
                </div>
                {isLoadingMarkdown ? (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    Rendering Markdown journal...
                  </div>
                ) : (
                  <pre className="p-3 rounded-md bg-muted/40 border border-border/60 text-[11px] text-foreground font-mono whitespace-pre-wrap leading-relaxed">
                    {markdownContent || `# ${activeDiary.title}\n\n${activeDiary.reflective_narrative}`}
                  </pre>
                )}
              </div>
            )
          ) : (
            <div className="p-12 text-center text-xs text-muted-foreground">
              Select a growth diary entry to inspect cognitive evolution details.
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
