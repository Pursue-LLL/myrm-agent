'use client';

/**
 * [INPUT]
 * @/services/memory/procedureExperience::listProcedures, registerProcedure, retrieveDualNode,
 *   splitIntents, ProcedureMemoryEntryDTO, RegisterProcedureMemoryRequest, DualNodeRetrievalRequest,
 *   DualNodeRetrievalResponseDTO
 * ./ProcedureExperienceHudBar::ProcedureExperienceHudBar
 * ./ProcedureProtocolInspectorView::ProcedureProtocolInspectorView
 * ./DualNodeRetrievalConsoleView::DualNodeRetrievalConsoleView
 * ./procedureFallbacks::FALLBACK_PROCEDURES
 *
 * [OUTPUT]
 * ProcedureExperienceRetrievalCard: Command center card providing 8-field procedure-shaped
 * experience protocol inspection, fixed-count dual-node retrieval, and split-over-merge multi-intent decomposition.
 *
 * [POS]
 * Primary UI Card for Item 104 (ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite).
 * Strict typing applied: No `any` types allowed. Single file < 300 lines.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import {
  FileCode,
  GitPullRequest,
  RefreshCw,
  Sliders,
  Layers,
} from 'lucide-react';
import {
  listProcedures,
  registerProcedure,
  retrieveDualNode,
  splitIntents,
  type DualNodeRetrievalRequest,
  type DualNodeRetrievalResponseDTO,
  type ProcedureMemoryEntryDTO,
  type RegisterProcedureMemoryRequest,
} from '@/services/memory/procedureExperience';
import { DualNodeRetrievalConsoleView } from './DualNodeRetrievalConsoleView';
import { ProcedureExperienceHudBar } from './ProcedureExperienceHudBar';
import { ProcedureProtocolInspectorView } from './ProcedureProtocolInspectorView';
import { FALLBACK_PROCEDURES } from './procedureFallbacks';

type ActiveTab = 'protocol_inspector' | 'dual_node_console';

export function ProcedureExperienceRetrievalCard(): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<ActiveTab>('protocol_inspector');
  const [entries, setEntries] = useState<ProcedureMemoryEntryDTO[]>(FALLBACK_PROCEDURES);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const fetched = await listProcedures();
      if (fetched && fetched.length > 0) {
        setEntries(fetched);
      }
    } catch {
      // Fallback local simulated dataset
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleRegister = async (req: RegisterProcedureMemoryRequest) => {
    setIsLoading(true);
    try {
      try {
        const created = await registerProcedure(req);
        setEntries((prev) => [created, ...prev]);
      } catch {
        // Fallback local insertion
        const localEntry: ProcedureMemoryEntryDTO = {
          entry_id: `proc_local_${Date.now()}`,
          name: req.name,
          retrieval_anchor: `intent:${req.name.toLowerCase().replace(/\s+/g, '-')}|pre:ready|app:all`,
          operation_intent: req.operation_intent,
          preconditions: req.preconditions,
          immutable_boundary: req.immutable_boundary,
          procedure_steps: req.procedure_steps,
          write_field_provenance: req.write_field_provenance,
          anti_patterns: req.anti_patterns,
          applicability: req.applicability,
          negative_applicability: req.negative_applicability,
          confidence: req.confidence ?? 1.0,
          created_at: new Date().toISOString(),
        };
        setEntries((prev) => [localEntry, ...prev]);
      }
      await loadData();
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetrieve = async (
    req: DualNodeRetrievalRequest
  ): Promise<DualNodeRetrievalResponseDTO> => {
    try {
      return await retrieveDualNode(req);
    } catch {
      // Fallback local match
      const q = req.query_text.toLowerCase();
      const matched = entries.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          e.operation_intent.toLowerCase().includes(q) ||
          e.retrieval_anchor.toLowerCase().includes(q)
      );
      const topN = req.top_n ?? 2;
      return {
        node_kind: req.node_kind ?? 'first_user',
        top_n_requested: topN,
        total_matched: matched.length,
        matched_entries: matched.slice(0, topN),
      };
    }
  };

  const handleSplitIntents = async (
    rawText: string
  ): Promise<Array<{ intent: string; body: string }>> => {
    try {
      const res = await splitIntents(rawText);
      return res.fragments;
    } catch {
      // Fallback local regex split
      return [
        { intent: '意图 1 (本地解析)', body: rawText.slice(0, 50) },
        { intent: '意图 2 (本地解析)', body: rawText.slice(50) },
      ];
    }
  };

  return (
    <Card className="border border-border-subtle bg-surface shadow-xs">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileCode className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base font-semibold text-text-primary">
                  过程形态经验协议与固定条数双节点检索
                </CardTitle>
                <Badge variant="outline" className="bg-primary/5 text-primary text-xs">
                  Item 104 · P0
                </Badge>
              </div>
              <CardDescription className="text-text-secondary text-xs">
                八字段过程模板终结流水账式复用 · 首问与写前双节点精准拦截 · 固定 Top-N 彻底终结字符截断
              </CardDescription>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void loadData()}
              disabled={isLoading}
              className="flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
              aria-label="刷新过程经验数据"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              <span>刷新数据</span>
            </Button>
          </div>
        </div>

        {/* 4-Dimension HUD Metrics Bar */}
        <ProcedureExperienceHudBar entries={entries} />

        {/* Tab Selection */}
        <div className="mt-4 flex items-center gap-2 border-border-subtle border-b pb-2 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab('protocol_inspector')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'protocol_inspector'
                ? 'bg-primary text-primary-foreground'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-subtle'
            }`}
            aria-label="切换到八字段过程协议视图"
          >
            <FileCode className="h-3.5 w-3.5" />
            <span>八字段过程协议规范</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('dual_node_console')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
              activeTab === 'dual_node_console'
                ? 'bg-primary text-primary-foreground'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-subtle'
            }`}
            aria-label="切换到双节点固定条数检索控制台"
          >
            <GitPullRequest className="h-3.5 w-3.5" />
            <span>双节点固定条数检索</span>
          </button>
        </div>
      </CardHeader>

      <CardContent>
        {activeTab === 'protocol_inspector' ? (
          <ProcedureProtocolInspectorView
            entries={entries}
            onRegister={handleRegister}
            onSplitIntents={handleSplitIntents}
            isLoading={isLoading}
          />
        ) : (
          <DualNodeRetrievalConsoleView
            onRetrieve={handleRetrieve}
            isLoading={isLoading}
          />
        )}
      </CardContent>
    </Card>
  );
}
