'use client';

/**
 * [INPUT]
 * @/services/memory/relationalBacktrack::TemporalRelationTripletDTO, RecordTripletRequestDTO, EntityTypeKind
 *
 * [OUTPUT]
 * RelationalAnchorGraphView: Subview for structured entity-action-temporal triplets,
 * synonym dialect mapping clusters, and verbatim quote evidence anchors.
 *
 * [POS]
 * Subcomponent for Item 100 (TemporalRelationalAnchorAndCrossSessionEntityBacktrackingSuite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Network,
  PlusCircle,
  Calendar,
  Quote,
  Sparkles,
  User,
  Building,
  Briefcase,
  Wrench,
  RotateCw,
  Hash,
} from 'lucide-react';
import type {
  EntityTypeKind,
  RecordTripletRequestDTO,
  TemporalRelationTripletDTO,
} from '@/services/memory/relationalBacktrack';

interface RelationalAnchorGraphViewProps {
  triplets: TemporalRelationTripletDTO[];
  onRecordTriplet: (request: RecordTripletRequestDTO) => Promise<void>;
  isLoading: boolean;
}

export function RelationalAnchorGraphView({
  triplets,
  onRecordTriplet,
  isLoading,
}: RelationalAnchorGraphViewProps): React.JSX.Element {
  const [action, setAction] = useState<string>('eat_hotpot');
  const [targetEntity, setTargetEntity] = useState<string>('张总');
  const [targetType, setTargetType] = useState<EntityTypeKind>('client');
  const [temporalAnchor, setTemporalAnchor] = useState<string>('2026-10-18');
  const [quote, setQuote] = useState<string>('周五晚上准备同客户张总去打边炉，商定下季度合作。');
  const [synonyms, setSynonyms] = useState<string>('吃火锅, 打边炉, 涮火锅');
  const [submitting, setSubmitting] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!action.trim() || !targetEntity.trim() || !quote.trim()) return;

    setSubmitting(true);
    try {
      const synList = synonyms
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      await onRecordTriplet({
        predicate_action: action.trim(),
        target_entity: targetEntity.trim(),
        target_entity_type: targetType,
        temporal_anchor: temporalAnchor.trim(),
        session_id: `sess-${Date.now()}`,
        message_id: `msg-${Date.now()}`,
        verbatim_quote: quote.trim(),
        action_synonyms: synList,
        confidence: 1.0,
      });

      setTargetEntity('');
      setQuote('');
    } finally {
      setSubmitting(false);
    }
  };

  const getEntityIcon = (type: EntityTypeKind) => {
    switch (type) {
      case 'client':
      case 'person':
        return <User className="w-3.5 h-3.5 text-blue-500" />;
      case 'organization':
        return <Building className="w-3.5 h-3.5 text-purple-500" />;
      case 'project':
        return <Briefcase className="w-3.5 h-3.5 text-amber-500" />;
      default:
        return <Wrench className="w-3.5 h-3.5 text-emerald-500" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Triplet Ingestion Form */}
      <div className="p-4 rounded-lg border border-border bg-card/60 backdrop-blur-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <PlusCircle className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              Anchor Structured Entity-Action-Temporal Triplet
            </span>
          </div>
          <span className="text-xs text-muted-foreground">
            Bridges colloquial dialect mismatch
          </span>
        </div>

        <form onSubmit={handleSubmit} aria-label="record-triplet-form" className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label htmlFor="triplet-action" className="block text-xs font-medium text-muted-foreground mb-1">
                Predicate Action (Canonical)
              </label>
              <input
                id="triplet-action"
                type="text"
                value={action}
                onChange={(e) => setAction(e.target.value)}
                placeholder="eat_hotpot, sign_contract..."
                className="w-full text-xs font-mono px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={submitting || isLoading}
              />
            </div>

            <div>
              <label htmlFor="triplet-entity" className="block text-xs font-medium text-muted-foreground mb-1">
                Target Entity Object
              </label>
              <input
                id="triplet-entity"
                type="text"
                value={targetEntity}
                onChange={(e) => setTargetEntity(e.target.value)}
                placeholder="李总, AcmeCorp..."
                className="w-full text-xs font-mono px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={submitting || isLoading}
              />
            </div>

            <div>
              <label htmlFor="triplet-type" className="block text-xs font-medium text-muted-foreground mb-1">
                Entity Category
              </label>
              <select
                id="triplet-type"
                value={targetType}
                onChange={(e) => setTargetType(e.target.value as EntityTypeKind)}
                className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={submitting || isLoading}
              >
                <option value="client">Client (客户)</option>
                <option value="person">Person (个人)</option>
                <option value="project">Project (项目)</option>
                <option value="organization">Organization (机构)</option>
                <option value="location">Location (地点)</option>
                <option value="tool">Tool (工具)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label htmlFor="triplet-date" className="block text-xs font-medium text-muted-foreground mb-1">
                Temporal Anchor (Date/Time)
              </label>
              <input
                id="triplet-date"
                type="text"
                value={temporalAnchor}
                onChange={(e) => setTemporalAnchor(e.target.value)}
                placeholder="2026-10-18"
                className="w-full text-xs font-mono px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={submitting || isLoading}
              />
            </div>

            <div>
              <label htmlFor="triplet-synonyms" className="block text-xs font-medium text-muted-foreground mb-1">
                Dialect Synonyms (Comma-separated)
              </label>
              <input
                id="triplet-synonyms"
                type="text"
                value={synonyms}
                onChange={(e) => setSynonyms(e.target.value)}
                placeholder="吃火锅, 打边炉, 涮火锅..."
                className="w-full text-xs font-mono px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                disabled={submitting || isLoading}
              />
            </div>
          </div>

          <div>
            <label htmlFor="triplet-quote" className="block text-xs font-medium text-muted-foreground mb-1">
              Verbatim Dialogue Quote (Pinned Evidence)
            </label>
            <input
              id="triplet-quote"
              type="text"
              value={quote}
              onChange={(e) => setQuote(e.target.value)}
              placeholder="Exact historical utterance from conversation..."
              className="w-full text-xs px-2.5 py-1.5 rounded-md border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              disabled={submitting || isLoading}
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[11px] text-muted-foreground flex items-center space-x-1">
              <Quote className="w-3.5 h-3.5 text-primary" />
              <span>Verbatim evidence binding prevents LLM name hallucination</span>
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
                  Recording Triplet...
                </>
              ) : (
                <>
                  <Sparkles className="w-3 h-3 mr-1" />
                  Anchor Relational Triplet
                </>
              )}
            </Button>
          </div>
        </form>
      </div>

      {/* Triplet Registry List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Network className="w-4 h-4 text-primary" />
            <h4 className="text-sm font-semibold text-foreground">
              Indexed Relational Triplets ({triplets.length})
            </h4>
          </div>
          <span className="text-xs text-muted-foreground">
            Bidi Inverted Indexes
          </span>
        </div>

        {triplets.length === 0 ? (
          <div className="p-8 text-center rounded-lg border border-dashed border-border text-muted-foreground text-xs">
            No temporal relational triplets indexed. Record one above to enable cross-session backtracking.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {triplets.map((trip) => (
              <div
                key={trip.triplet_id}
                className="p-3.5 rounded-lg border border-border bg-card/40 space-y-2 hover:border-primary/40 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="space-y-0.5">
                    <div className="flex items-center space-x-1.5">
                      {getEntityIcon(trip.target_entity_type)}
                      <span className="text-xs font-semibold text-foreground font-mono">
                        {trip.target_entity}
                      </span>
                      <Badge variant="outline" className="text-[9px] uppercase font-mono">
                        {trip.target_entity_type}
                      </Badge>
                    </div>
                    <div className="text-[10px] text-muted-foreground flex items-center space-x-1">
                      <Calendar className="w-3 h-3 text-muted-foreground inline" />
                      <span>{trip.temporal_anchor}</span>
                    </div>
                  </div>
                  <Badge variant="default" className="text-[9px] font-mono bg-primary">
                    Action: {trip.predicate_action}
                  </Badge>
                </div>

                <div className="p-2 rounded bg-muted/40 border border-border/50 text-xs text-foreground/90 font-mono">
                  <span className="text-muted-foreground">“{trip.verbatim_quote}”</span>
                </div>

                {trip.action_synonyms.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                    <span className="text-[10px] text-muted-foreground flex items-center">
                      <Hash className="w-2.5 h-2.5 mr-0.5" /> Synonyms:
                    </span>
                    {trip.action_synonyms.map((s) => (
                      <Badge key={s} variant="outline" className="text-[9px] text-muted-foreground">
                        {s}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
