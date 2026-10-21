/**
 * [INPUT] rawContent, deliverableType, artifactTitle, onPatchCommit
 * [OUTPUT] DeliverableInspector component integrating outline navigation, active node inspection,
 *          selective partial patching and snapshot diff rollback
 * [POS] artifacts/deliverable-inspector/DeliverableInspector.tsx
 */

'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Sparkles,
  History,
  FileCheck,
  Maximize2,
  Minimize2,
  Layers,
  ChevronRight,
} from 'lucide-react';
import type {
  DeliverableType,
  DeliverableNode,
  DeliverableSnapshot,
  SelectivePatchRequest,
} from './deliverableInspectorTypes';
import {
  parseDeliverableNodes,
  applySelectiveNodePatch,
  computeSnapshotDiff,
} from './deliverableAstParser';
import { DeliverableOutlineNavigator } from './DeliverableOutlineNavigator';
import { DeliverableNodePatchBar } from './DeliverableNodePatchBar';
import { DeliverableSnapshotDiffModal } from './DeliverableSnapshotDiffModal';

export interface DeliverableInspectorProps {
  rawContent: string;
  deliverableType: DeliverableType;
  artifactTitle?: string;
  onPatchCommit?: (updatedNodes: DeliverableNode[], snapshot: DeliverableSnapshot) => void;
  onRollbackCommit?: (snapshot: DeliverableSnapshot) => void;
  className?: string;
}

export const DeliverableInspector: React.FC<DeliverableInspectorProps> = ({
  rawContent,
  deliverableType,
  artifactTitle = '未命名办公交付物',
  onPatchCommit,
  onRollbackCommit,
  className = '',
}) => {
  const [nodes, setNodes] = useState<DeliverableNode[]>([]);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<DeliverableSnapshot[]>([]);
  const [currentVersion, setCurrentVersion] = useState<number>(1);
  const [isDiffModalOpen, setIsDiffModalOpen] = useState<boolean>(false);
  const [isPatching, setIsPatching] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Initialize initial nodes and v1 snapshot
  useEffect(() => {
    const parsed = parseDeliverableNodes(rawContent, deliverableType);
    setNodes(parsed);
    if (parsed.length > 0 && parsed[0]) {
      setActiveNodeId(parsed[0].id);
    }
    const initialSnapshot: DeliverableSnapshot = {
      version: 1,
      timestamp: Date.now(),
      deliverableType,
      nodes: parsed,
      changeDescription: '初始全量生成',
    };
    setSnapshots([initialSnapshot]);
    setCurrentVersion(1);
  }, [rawContent, deliverableType]);

  const activeNode = useMemo(() => {
    if (!activeNodeId) {
      return null;
    }
    return nodes.find((n) => n.id === activeNodeId) || null;
  }, [nodes, activeNodeId]);

  const handleApplyPatch = useCallback(
    (request: SelectivePatchRequest) => {
      setIsPatching(true);

      // Simulate partial targeted patch applied to targeted node only
      setTimeout(() => {
        const target = nodes.find((n) => n.id === request.nodeId);
        const originalContent = target ? target.content : '';
        const patchedContent = `${originalContent}\n\n<!-- 局部定向更新: ${request.targetedPrompt} -->`;

        const updatedNodes = applySelectiveNodePatch(
          nodes,
          request.nodeId,
          patchedContent,
        );

        const newVersion = currentVersion + 1;
        const newSnapshot: DeliverableSnapshot = {
          version: newVersion,
          timestamp: Date.now(),
          deliverableType,
          nodes: updatedNodes,
          changeDescription: `定向微调 #${target ? target.index : ''}: ${request.targetedPrompt}`,
          patchedNodeId: request.nodeId,
        };

        setNodes(updatedNodes);
        setSnapshots((prev) => [...prev, newSnapshot]);
        setCurrentVersion(newVersion);
        setIsPatching(false);

        if (onPatchCommit) {
          onPatchCommit(updatedNodes, newSnapshot);
        }
      }, 300);
    },
    [nodes, currentVersion, deliverableType, onPatchCommit],
  );

  const handleRollback = useCallback(
    (targetVersion: number) => {
      const targetSnapshot = snapshots.find((s) => s.version === targetVersion);
      if (!targetSnapshot) {
        return;
      }

      setNodes(targetSnapshot.nodes);
      setCurrentVersion(targetSnapshot.version);
      if (targetSnapshot.nodes.length > 0 && targetSnapshot.nodes[0]) {
        setActiveNodeId(targetSnapshot.nodes[0].id);
      }

      if (onRollbackCommit) {
        onRollbackCommit(targetSnapshot);
      }
    },
    [snapshots, onRollbackCommit],
  );

  const diffItems = useMemo(() => {
    if (snapshots.length < 2) {
      return [];
    }
    const previousSnapshot = snapshots[snapshots.length - 2];
    if (!previousSnapshot) {
      return [];
    }
    return computeSnapshotDiff(previousSnapshot.nodes, nodes);
  }, [snapshots, nodes]);

  return (
    <div
      data-testid="deliverable-inspector"
      className={`flex flex-col rounded-xl border border-border/70 bg-card text-card-foreground shadow-sm overflow-hidden ${
        isFullscreen ? 'fixed inset-4 z-50 shadow-2xl' : 'h-[620px]'
      } ${className}`}
    >
      {/* Top Header */}
      <div className="flex items-center justify-between border-b px-4 py-2.5 bg-muted/20">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary border border-primary/20">
            <Layers className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-foreground tracking-tight">
                {artifactTitle}
              </span>
              <span className="rounded bg-primary/10 text-primary px-1.5 py-0.2 text-[10px] font-mono font-medium">
                v{currentVersion}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => {
              setIsDiffModalOpen(true);
            }}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-muted/40 hover:bg-muted px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <History className="h-3.5 w-3.5" />
            <span>版本对比 ({snapshots.length})</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setIsFullscreen((prev) => !prev);
            }}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label={isFullscreen ? '退出全屏' : '全屏核验'}
          >
            {isFullscreen ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Main Workspace (Split View) */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Navigator (240px) */}
        <div className="w-60 shrink-0 h-full">
          <DeliverableOutlineNavigator
            nodes={nodes}
            activeNodeId={activeNodeId}
            onSelectNode={setActiveNodeId}
            deliverableType={deliverableType}
          />
        </div>

        {/* Center Canvas / Content Viewer */}
        <div className="flex-1 flex flex-col h-full overflow-hidden bg-background">
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {activeNode ? (
              <div className="max-w-2xl mx-auto space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-border/60">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-primary bg-primary/10 px-2 py-0.5 rounded">
                      #{activeNode.index}
                    </span>
                    <h2 className="text-sm font-semibold text-foreground">
                      {activeNode.title}
                    </h2>
                  </div>
                  {activeNode.metadata?.lastPatchedAt && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
                      <Sparkles className="h-3 w-3" />
                      已局部定向修正
                    </span>
                  )}
                </div>

                <div className="rounded-lg border border-border/50 bg-card p-4 text-xs font-mono whitespace-pre-wrap leading-relaxed text-foreground select-text shadow-2xs">
                  {activeNode.content}
                </div>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                请从左侧大纲选择要核验的节点
              </div>
            )}
          </div>

          {/* Bottom Selective Patch Bar */}
          {activeNode && (
            <div className="p-3 border-t border-border/60 bg-card/60 backdrop-blur-sm">
              <DeliverableNodePatchBar
                targetNode={activeNode}
                onApplyPatch={handleApplyPatch}
                onClose={() => {
                  setActiveNodeId(null);
                }}
                isPatching={isPatching}
              />
            </div>
          )}
        </div>
      </div>

      {/* Snapshot Diff Modal */}
      <DeliverableSnapshotDiffModal
        isOpen={isDiffModalOpen}
        snapshots={snapshots}
        currentVersion={currentVersion}
        diffItems={diffItems}
        onRollback={handleRollback}
        onClose={() => {
          setIsDiffModalOpen(false);
        }}
      />
    </div>
  );
};
