'use client';

/**
 * [INPUT]
 * @/services/memory/ephemeralDelta::EphemeralDeltaItemDTO, RecordDeltaRequestDTO
 *
 * [OUTPUT]
 * EphemeralDeltaLiveInspectorView: Subview for real-time turn-scoped delta inspection,
 * recording interactive user overrides with LWW deduplication, and verifying frozen prefix status.
 *
 * [POS]
 * Subcomponent for Item 98 (PromptCachePreservingEphemeralDeltaMemorySuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Zap,
  PlusCircle,
  Tag,
  ShieldCheck,
  RotateCw,
  Hash,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import type {
  DeltaAction,
  DeltaSource,
  EphemeralDeltaItemDTO,
  RecordDeltaRequestDTO,
} from '@/services/memory/ephemeralDelta';

interface EphemeralDeltaLiveInspectorViewProps {
  sessionId: string;
  deltas: EphemeralDeltaItemDTO[];
  isReconciled: boolean;
  onRecordDelta: (request: RecordDeltaRequestDTO) => Promise<void>;
  isLoading: boolean;
}

export function EphemeralDeltaLiveInspectorView({
  sessionId,
  deltas,
  isReconciled,
  onRecordDelta,
  isLoading,
}: EphemeralDeltaLiveInspectorViewProps): React.JSX.Element {
  const [targetKey, setTargetKey] = useState<string>('');
  const [content, setContent] = useState<string>('');
  const [action, setAction] = useState<DeltaAction>('override');
  const [source, setSource] = useState<DeltaSource>('user_explicit');
  const [turnIndex, setTurnIndex] = useState<number>(deltas.length + 1);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!targetKey.trim() || !content.trim()) {
      setFormError('Key and Content must not be empty.');
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      await onRecordDelta({
        session_id: sessionId,
        target_key: targetKey.trim(),
        content: content.trim(),
        action,
        source,
        turn_index: turnIndex,
        confidence: 1.0,
      });
      setTargetKey('');
      setContent('');
      setTurnIndex((prev) => prev + 1);
    } catch {
      setFormError('Failed to record ephemeral delta.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Live Delta Insertion Form */}
      <div className="p-4 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <PlusCircle className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              Record In-Flight Transient Delta
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            Bypasses System Prompt prefix rewrite
          </span>
        </div>

        {formError && (
          <div
            role="alert"
            className="flex items-center space-x-2 p-2 rounded bg-destructive/10 text-destructive text-xs"
          >
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{formError}</span>
          </div>
        )}

        <form aria-label="record-delta-form" onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label
                htmlFor="delta-target-key"
                className="block text-xs font-medium text-muted-foreground mb-1"
              >
                Target Key
              </label>
              <input
                id="delta-target-key"
                type="text"
                placeholder="e.g. user_nickname"
                value={targetKey}
                onChange={(e) => setTargetKey(e.target.value)}
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={submitting}
              />
            </div>
            <div>
              <label
                htmlFor="delta-action-select"
                className="block text-xs font-medium text-muted-foreground mb-1"
              >
                Action Semantic
              </label>
              <select
                id="delta-action-select"
                value={action}
                onChange={(e) => setAction(e.target.value as DeltaAction)}
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={submitting}
              >
                <option value="override">Override (Last-Write-Wins)</option>
                <option value="add_fact">Add Fact (Incremental)</option>
                <option value="revoke">Revoke (Tombstone)</option>
              </select>
            </div>
            <div>
              <label
                htmlFor="delta-source-select"
                className="block text-xs font-medium text-muted-foreground mb-1"
              >
                Source Origin
              </label>
              <select
                id="delta-source-select"
                value={source}
                onChange={(e) => setSource(e.target.value as DeltaSource)}
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={submitting}
              >
                <option value="user_explicit">User Explicit Correction</option>
                <option value="agent_inferred">Agent Inferred Fact</option>
              </select>
            </div>
          </div>

          <div>
            <label
              htmlFor="delta-content-input"
              className="block text-xs font-medium text-muted-foreground mb-1"
            >
              Delta Content / Override Value
            </label>
            <input
              id="delta-content-input"
              type="text"
              placeholder="e.g. Please address me as Old Zhang in subsequent turns"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              disabled={submitting}
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[11px] text-muted-foreground flex items-center space-x-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              <span>KV Cache safe: Appended to final turn HumanMessage</span>
            </span>
            <Button
              type="submit"
              size="sm"
              disabled={submitting || isLoading}
              className="text-xs focus:ring-2 focus:ring-primary"
            >
              {submitting ? (
                <>
                  <RotateCw className="w-3 h-3 mr-1 animate-spin" />
                  Recording...
                </>
              ) : (
                <>
                  <Zap className="w-3 h-3 mr-1" />
                  Mount Ephemeral Delta
                </>
              )}
            </Button>
          </div>
        </form>
      </div>

      {/* Active Delta List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Tag className="w-4 h-4 text-muted-foreground" />
            <h4 className="text-sm font-semibold text-foreground">
              In-Flight Active Deltas ({deltas.length})
            </h4>
          </div>
          <div className="flex items-center space-x-2 text-xs">
            {isReconciled ? (
              <Badge variant="outline" className="text-emerald-600 border-emerald-500/40 text-[10px]">
                <CheckCircle2 className="w-3 h-3 mr-1 inline" /> Reconciled to Store
              </Badge>
            ) : (
              <Badge variant="default" className="text-[10px] bg-primary">
                Transient Active
              </Badge>
            )}
          </div>
        </div>

        {deltas.length === 0 ? (
          <div className="p-6 text-center rounded-lg border border-dashed border-border text-muted-foreground text-xs">
            No active ephemeral deltas mounted for session <code className="font-mono">{sessionId}</code>.
            Add one above to test cache-safe prompt updates.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {deltas.map((delta) => (
              <div
                key={delta.delta_id}
                className="p-3.5 rounded-lg border border-border bg-card/40 space-y-2 hover:border-primary/40 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="space-y-0.5">
                    <div className="flex items-center space-x-1.5">
                      <Hash className="w-3.5 h-3.5 text-primary" />
                      <span className="text-xs font-mono font-semibold text-foreground">
                        {delta.target_key}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground">
                      Turn {delta.turn_index} • {delta.source}
                    </span>
                  </div>
                  <Badge
                    variant={delta.action === 'override' ? 'default' : 'outline'}
                    className="text-[9px] uppercase tracking-wider"
                  >
                    {delta.action}
                  </Badge>
                </div>

                <p className="text-xs text-foreground bg-muted/40 p-2 rounded border border-border/50 font-mono">
                  {delta.content}
                </p>

                <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1">
                  <span>Confidence: {(delta.confidence * 100).toFixed(0)}%</span>
                  <span className="font-mono">
                    {new Date(delta.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
