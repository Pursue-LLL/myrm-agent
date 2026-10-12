'use client';

/**
 * [INPUT]
 * @/services/memory/relationalBacktrack::RelationalBacktrackResponseDTO,
 *   RelationalBacktrackQueryRequestDTO, EntityTypeKind
 *
 * [OUTPUT]
 * CrossSessionBacktrackConsoleView: Subview for querying cross-session entity backtracking
 * from colloquial action cues (e.g. '打边炉' -> '李总'), showing synthesized answers and verbatim quote evidence.
 *
 * [POS]
 * Subcomponent for Item 100 (TemporalRelationalAnchorAndCrossSessionEntityBacktrackingSuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Search,
  Sparkles,
  UserCheck,
  Calendar,
  Quote,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  RotateCw,
  Compass,
} from 'lucide-react';
import type {
  EntityTypeKind,
  RelationalBacktrackQueryRequestDTO,
  RelationalBacktrackResponseDTO,
} from '@/services/memory/relationalBacktrack';

interface CrossSessionBacktrackConsoleViewProps {
  backtrackResult: RelationalBacktrackResponseDTO | null;
  onQueryBacktrack: (request: RelationalBacktrackQueryRequestDTO) => Promise<void>;
  isLoading: boolean;
}

export function CrossSessionBacktrackConsoleView({
  backtrackResult,
  onQueryBacktrack,
  isLoading,
}: CrossSessionBacktrackConsoleViewProps): React.JSX.Element {
  const [cue, setCue] = useState<string>('打边炉');
  const [entityType, setEntityType] = useState<EntityTypeKind | ''>('client');
  const [minConf, setMinConf] = useState<number>(0.5);

  const handleSearch = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!cue.trim()) return;

    await onQueryBacktrack({
      action_cue: cue.trim(),
      target_entity_type: entityType ? (entityType as EntityTypeKind) : undefined,
      min_confidence: minConf,
    });
  };

  const handleQuickPreset = async (presetCue: string, presetType: EntityTypeKind | '') => {
    setCue(presetCue);
    setEntityType(presetType);
    await onQueryBacktrack({
      action_cue: presetCue,
      target_entity_type: presetType ? (presetType as EntityTypeKind) : undefined,
      min_confidence: minConf,
    });
  };

  const hits = backtrackResult?.hits ?? [];

  return (
    <div className="space-y-6">
      {/* Backtrack Query Form */}
      <div className="p-4 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Compass className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              Cross-Session Relational Entity Backtracking Console
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            Dialect Synonym & Causal Inversion
          </span>
        </div>

        <form onSubmit={handleSearch} aria-label="backtrack-query-form" className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="md:col-span-2">
              <label htmlFor="backtrack-cue-input" className="block text-xs font-medium text-muted-foreground mb-1">
                Colloquial Action Cue / Dialect Question
              </label>
              <input
                id="backtrack-cue-input"
                type="text"
                value={cue}
                onChange={(e) => setCue(e.target.value)}
                placeholder="上次说去打边炉是同边个客？/ 哪天签约的？"
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={isLoading}
              />
            </div>

            <div>
              <label htmlFor="backtrack-type-select" className="block text-xs font-medium text-muted-foreground mb-1">
                Target Entity Category
              </label>
              <select
                id="backtrack-type-select"
                value={entityType}
                onChange={(e) => setEntityType(e.target.value as EntityTypeKind | '')}
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={isLoading}
              >
                <option value="">Any Category (全部类别)</option>
                <option value="client">Client (客户)</option>
                <option value="person">Person (个人)</option>
                <option value="project">Project (项目)</option>
                <option value="organization">Organization (机构)</option>
              </select>
            </div>
          </div>

          {/* Quick presets */}
          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center space-x-2 flex-wrap text-xs text-muted-foreground">
              <span className="text-[11px]">Presets:</span>
              <button
                type="button"
                onClick={() => void handleQuickPreset('打边炉', 'client')}
                disabled={isLoading}
                className="text-[11px] underline text-primary hover:text-primary/80 focus:ring-2 focus:ring-primary rounded"
              >
                #打边炉 (Client)
              </button>
              <button
                type="button"
                onClick={() => void handleQuickPreset('开会', 'person')}
                disabled={isLoading}
                className="text-[11px] underline text-primary hover:text-primary/80 focus:ring-2 focus:ring-primary rounded"
              >
                #开会 (Person)
              </button>
              <button
                type="button"
                onClick={() => void handleQuickPreset('签约', 'client')}
                disabled={isLoading}
                className="text-[11px] underline text-primary hover:text-primary/80 focus:ring-2 focus:ring-primary rounded"
              >
                #签约 (Client)
              </button>
            </div>

            <Button
              type="submit"
              size="sm"
              disabled={isLoading || !cue.trim()}
              className="text-xs shrink-0 focus:ring-2 focus:ring-primary"
            >
              {isLoading ? (
                <>
                  <RotateCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                  Backtracking...
                </>
              ) : (
                <>
                  <Search className="w-3.5 h-3.5 mr-1" />
                  Backtrack Entity
                </>
              )}
            </Button>
          </div>
        </form>
      </div>

      {/* Synthesized Answer Banner */}
      {backtrackResult?.inferred_answer && (
        <div className="p-4 rounded-lg border border-primary/40 bg-primary/5 space-y-1.5">
          <div className="flex items-center space-x-1.5 text-primary text-xs font-semibold">
            <Sparkles className="w-4 h-4" />
            <span>Definitive Causal Relational Deduction</span>
          </div>
          <p className="text-xs text-foreground font-medium leading-relaxed">
            {backtrackResult.inferred_answer}
          </p>
        </div>
      )}

      {/* Hits List & Verbatim Evidence */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-foreground flex items-center space-x-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            <span>Matched Relational Evidences ({hits.length})</span>
          </h4>
          <span className="text-xs text-muted-foreground font-mono">
            Zero Lost-in-the-Middle
          </span>
        </div>

        {hits.length === 0 ? (
          <div className="p-8 text-center rounded-lg border border-dashed border-border text-muted-foreground text-xs">
            <HelpCircle className="w-6 h-6 mx-auto mb-2 opacity-50" />
            No matching relation triplets found for cue &quot;{cue}&quot;. Click a preset above to test dialect inversion.
          </div>
        ) : (
          <div className="space-y-3">
            {hits.map((hit) => {
              const trip = hit.triplet;
              return (
                <div
                  key={trip.triplet_id}
                  className="p-4 rounded-lg border border-border bg-card/60 space-y-2.5 hover:border-primary/40 transition-colors"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center space-x-2">
                      <UserCheck className="w-4 h-4 text-primary" />
                      <span className="text-sm font-bold text-foreground font-mono">
                        {trip.target_entity}
                      </span>
                      <Badge variant="outline" className="text-[9px] uppercase font-mono">
                        {trip.target_entity_type}
                      </Badge>
                      <Badge variant="default" className="text-[9px] bg-emerald-600">
                        Score: {(hit.match_score * 100).toFixed(0)}%
                      </Badge>
                    </div>

                    <div className="flex items-center space-x-2 text-xs text-muted-foreground">
                      <span className="flex items-center space-x-1 font-mono text-[11px]">
                        <Calendar className="w-3.5 h-3.5 inline text-muted-foreground" />
                        <span>{trip.temporal_anchor}</span>
                      </span>
                      <span className="text-[10px] bg-muted/60 px-2 py-0.5 rounded font-mono">
                        {trip.session_id}
                      </span>
                    </div>
                  </div>

                  {/* Verbatim quote highlight bubble */}
                  <div className="p-3 rounded-md border border-primary/20 bg-accent/30 space-y-1">
                    <div className="flex items-center space-x-1 text-[11px] text-primary font-medium">
                      <Quote className="w-3 h-3" />
                      <span>Historical Verbatim Dialogue Evidence</span>
                    </div>
                    <p className="text-xs text-foreground font-mono italic">
                      &ldquo;{trip.verbatim_quote}&rdquo;
                    </p>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span className="font-mono">Canonical Action: {trip.predicate_action}</span>
                    <span className="text-emerald-600 font-medium">Verified Historical Record</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
