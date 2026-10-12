/**
 * [INPUT]
 * @/services/memory::CognitiveConsolidationRequestDTO, CognitiveConsolidationReportDTO
 * onTriggerConsolidation: (payload: CognitiveConsolidationRequestDTO) => Promise<CognitiveConsolidationReportDTO>
 * isConsolidating: boolean, latestReport?: CognitiveConsolidationReportDTO | null
 *
 * [OUTPUT]
 * Component: DreamCognitiveSynthesisConsoleView
 *
 * [POS]
 * Trigger console and real-time execution report view for Item 125 Dream Cognitive Consolidation.
 * Follows a11y ratchet guidelines: Uses native `<section aria-label="...">`, visible focus rings,
 * proper htmlFor connections, and zero raw `>` or `->` characters.
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Play, Sparkles, Box, CheckCircle2, Clock } from 'lucide-react';
import type {
  CognitiveConsolidationReportDTO,
  CognitiveConsolidationRequestDTO,
} from '@/services/memory';

interface DreamCognitiveSynthesisConsoleViewProps {
  onTriggerConsolidation: (
    payload: CognitiveConsolidationRequestDTO,
  ) => Promise<CognitiveConsolidationReportDTO>;
  isConsolidating: boolean;
  latestReport: CognitiveConsolidationReportDTO | null;
}

export const DreamCognitiveSynthesisConsoleView: React.FC<DreamCognitiveSynthesisConsoleViewProps> = ({
  onTriggerConsolidation,
  isConsolidating,
  latestReport,
}) => {
  const [selectedCube, setSelectedCube] = useState<string>('cube-proj-open-perplexity');
  const [sessionInput, setSessionInput] = useState<string>('session-live-202');
  const [factText, setFactText] = useState<string>(
    'Developer strictly mandates 100% clean architecture, no Any types, and thorough test gates.'
  );

  const handleRunDream = async () => {
    if (!factText.trim()) return;
    const payload: CognitiveConsolidationRequestDTO = {
      cube_id: selectedCube || undefined,
      fragments: [
        {
          session_id: sessionInput.trim() || 'session-custom-01',
          chat_turn_count: 3,
          memories: [
            {
              content: factText.trim(),
              evidence: [
                {
                  message_id: 'msg-input-01',
                  speaker: 'user',
                  verbatim_quote: factText.trim(),
                },
              ],
            },
          ],
        },
      ],
    };
    await onTriggerConsolidation(payload);
  };

  return (
    <section
      aria-label="Dream Cognitive Synthesis Console"
      className="p-5 rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/40 pb-3">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-500" aria-hidden="true" />
            Background Dream Reflection &amp; Insight Synthesis Console
          </h3>
          <p className="text-xs text-muted-foreground">
            Dispatch non-blocking dreaming cycles across session fragments to extract high-order invariants.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
        {/* Left Form: Configure Fragments and Trigger Dream */}
        <div className="md:col-span-6 space-y-3.5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="dream-cube-select" className="block text-xs font-medium text-foreground mb-1">
                Target Memory Cube:
              </label>
              <select
                id="dream-cube-select"
                value={selectedCube}
                onChange={(e) => setSelectedCube(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground font-mono"
              >
                <option value="cube-proj-open-perplexity">cube-proj-open-perplexity</option>
                <option value="cube-global-shared">cube-global-shared</option>
                <option value="cube-agent-architect-private">cube-agent-architect-private</option>
              </select>
            </div>
            <div>
              <label htmlFor="dream-session-input" className="block text-xs font-medium text-foreground mb-1">
                Session Identifier:
              </label>
              <input
                id="dream-session-input"
                type="text"
                value={sessionInput}
                onChange={(e) => setSessionInput(e.target.value)}
                placeholder="e.g. session-live-202"
                className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground font-mono"
              />
            </div>
          </div>

          <div>
            <label htmlFor="dream-fact-input" className="block text-xs font-medium text-foreground mb-1">
              Observed Memory Fact / Engineering Directive:
            </label>
            <textarea
              id="dream-fact-input"
              rows={3}
              value={factText}
              onChange={(e) => setFactText(e.target.value)}
              placeholder="Record developer directive or architectural insight..."
              className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:ring-2 focus:ring-primary focus:outline-none text-foreground leading-relaxed"
            />
          </div>

          <button
            type="button"
            onClick={handleRunDream}
            disabled={isConsolidating || !factText.trim()}
            className="w-full py-2 px-4 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:ring-2 focus:ring-primary focus:outline-none disabled:opacity-50 inline-flex items-center justify-center gap-2"
          >
            <Play className={`w-3.5 h-3.5 ${isConsolidating ? 'animate-pulse' : ''}`} aria-hidden="true" />
            <span>{isConsolidating ? 'Synthesizing Cognitive Insights...' : 'Trigger Dream Consolidation'}</span>
          </button>
        </div>

        {/* Right Pane: Execution Report */}
        <div className="md:col-span-6 p-4 rounded-lg border border-border/60 bg-muted/10 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-blue-500" aria-hidden="true" />
              Consolidation Execution Report
            </span>
            {latestReport && (
              <span className="inline-flex items-center gap-1 text-[11px] font-mono text-emerald-600 dark:text-emerald-400 font-semibold">
                <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
                Completed ({latestReport.duration_ms.toFixed(1)} ms)
              </span>
            )}
          </div>

          {latestReport ? (
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2 rounded bg-card border border-border/40 text-center">
                  <div className="text-[11px] text-muted-foreground">Facts Processed</div>
                  <div className="text-sm font-bold text-foreground">{latestReport.input_fact_count}</div>
                </div>
                <div className="p-2 rounded bg-card border border-border/40 text-center">
                  <div className="text-[11px] text-muted-foreground">Clusters Formed</div>
                  <div className="text-sm font-bold text-purple-600 dark:text-purple-400">
                    {latestReport.clusters_formed}
                  </div>
                </div>
                <div className="p-2 rounded bg-card border border-border/40 text-center">
                  <div className="text-[11px] text-muted-foreground">Actions Mutated</div>
                  <div className="text-sm font-bold text-primary">{latestReport.actions_generated}</div>
                </div>
              </div>

              {/* Render newly generated diary if available */}
              {latestReport.diary_entries.length > 0 && (
                <div className="p-2.5 rounded-md bg-card border border-border/40 space-y-1">
                  <div className="text-[11px] font-semibold text-foreground">
                    Synthesized Diary: {latestReport.diary_entries[0]?.title}
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-2">
                    {latestReport.diary_entries[0]?.summary}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="p-10 text-center text-xs text-muted-foreground border border-dashed rounded-md">
              No consolidation run executed in current session. Submit fragments to initiate cognitive dreaming.
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
