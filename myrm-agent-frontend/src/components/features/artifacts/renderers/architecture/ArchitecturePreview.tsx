'use client';

import React, { memo, useState, useMemo, useCallback, useRef } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import { toast } from '@/hooks/shared/useToast';
import {
  Search,
  Download,
  GitCompare,
  RefreshCw,
  ZoomIn,
  Eye,
  Plus,
  Minus,
  Move,
  Copy,
  Check,
  Route,
} from 'lucide-react';
import type { ArchitectureIR } from './types';
import {
  computeDagreLayout,
  sanitizeArchitectureIR,
  traceFullConnectedCausalityGraph,
  findShortestPath,
  type PathTraceResult,
} from './layout';
import { computeArchitectureDiff } from './diff';
import { ArchitectureCustomNode } from './ArchitectureCustomNode';
import type { ArtifactVersion } from '@/store/chat/types';
import html2canvas from 'html2canvas';
import MermaidPreview from '../MermaidPreview';

const nodeTypes = {
  archNode: ArchitectureCustomNode,
};

interface ArchitecturePreviewProps {
  content: string;
  versions?: ArtifactVersion[];
  viewingVersionIndex?: number;
  initialDiffMode?: boolean;
}

export const ArchitecturePreview: React.FC<ArchitecturePreviewProps> = memo(
  ({ content, versions, viewingVersionIndex = -1, initialDiffMode = false }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [targetNodeId, setTargetNodeId] = useState<string | null>(null);
    const [isDiffMode, setIsDiffMode] = useState(initialDiffMode);
    const [isCopied, setIsCopied] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    // Parse current IR
    const currentIR = useMemo<ArchitectureIR | null>(() => {
      try {
        const parsed = JSON.parse(content);
        return sanitizeArchitectureIR(parsed);
      } catch {
        return null;
      }
    }, [content]);

    // Parse previous IR if available
    const previousIR = useMemo<ArchitectureIR | null>(() => {
      if (!versions || versions.length < 2) {
        return null;
      }
      const targetIdx = viewingVersionIndex >= 0 ? viewingVersionIndex + 1 : 1;
      const prevVersion = versions[targetIdx];
      if (!prevVersion || !prevVersion.content) {
        return null;
      }
      try {
        const parsed = JSON.parse(prevVersion.content);
        return sanitizeArchitectureIR(parsed);
      } catch {
        return null;
      }
    }, [versions, viewingVersionIndex]);

    // Compute effective IR based on Diff Toggle
    const activeIR = useMemo<ArchitectureIR | null>(() => {
      if (!currentIR) {
        return null;
      }
      if (isDiffMode && previousIR) {
        return computeArchitectureDiff(previousIR, currentIR);
      }
      return currentIR;
    }, [currentIR, previousIR, isDiffMode]);

    // Compute Dagre layout
    const initialElements = useMemo(() => {
      if (!activeIR) {
        return { nodes: [], edges: [] };
      }
      return computeDagreLayout(activeIR);
    }, [activeIR]);

    // Compute Diff Summary Stats
    const diffSummary = useMemo(() => {
      if (!isDiffMode || !activeIR) {
        return null;
      }
      let addedNodes = 0;
      let deletedNodes = 0;
      let modifiedNodes = 0;
      let addedEdges = 0;
      let deletedEdges = 0;

      for (const n of activeIR.nodes) {
        if (n.diffState === 'added') {
          addedNodes++;
        }
        if (n.diffState === 'deleted') {
          deletedNodes++;
        }
        if (n.diffState === 'modified') {
          modifiedNodes++;
        }
      }
      for (const e of activeIR.edges) {
        if (e.diffState === 'added') {
          addedEdges++;
        }
        if (e.diffState === 'deleted') {
          deletedEdges++;
        }
      }

      return { addedNodes, deletedNodes, modifiedNodes, addedEdges, deletedEdges };
    }, [isDiffMode, activeIR]);

    const [nodes, setNodes, onNodesChange] = useNodesState(initialElements.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialElements.edges);

    // Sync layout when activeIR changes
    React.useEffect(() => {
      setNodes(initialElements.nodes);
      setEdges(initialElements.edges);
    }, [initialElements, setNodes, setEdges]);

    // Calculate shortest path when both selectedNodeId (Start) and targetNodeId (End) are active
    const shortestPathResult = useMemo<PathTraceResult | null>(() => {
      if (!selectedNodeId || !targetNodeId || !activeIR) {
        return null;
      }
      return findShortestPath(selectedNodeId, targetNodeId, activeIR.edges);
    }, [selectedNodeId, targetNodeId, activeIR]);

    // Calculate highlighted nodes: either two-point shortest path, or single-node causality graph
    const highlightedNodeIds = useMemo<Set<string> | null>(() => {
      if (shortestPathResult && shortestPathResult.found) {
        return new Set(shortestPathResult.nodeIds);
      }
      if (!selectedNodeId || !activeIR) {
        return null;
      }
      return traceFullConnectedCausalityGraph(selectedNodeId, activeIR.edges);
    }, [shortestPathResult, selectedNodeId, activeIR]);

    const highlightedEdgeIds = useMemo<Set<string> | null>(() => {
      if (shortestPathResult && shortestPathResult.found) {
        return new Set(shortestPathResult.edgeIds);
      }
      return null;
    }, [shortestPathResult]);

    // Update node states based on search and connected path tracing
    const displayNodes = useMemo(() => {
      const query = searchQuery.trim().toLowerCase();
      return nodes.map((node) => {
        const label = String(node.data?.label || '').toLowerCase();
        const matchesSearch = query ? label.includes(query) : true;
        const isConnected = highlightedNodeIds ? highlightedNodeIds.has(node.id) : true;

        return {
          ...node,
          data: {
            ...node.data,
            isHighlighted: node.id === selectedNodeId || node.id === targetNodeId,
            isDimmed: (!matchesSearch || !isConnected) && Boolean(query || selectedNodeId || targetNodeId),
          },
        };
      });
    }, [nodes, searchQuery, selectedNodeId, targetNodeId, highlightedNodeIds]);

    // Update edge states for shortest path animation and stroke emphasis
    const displayEdges = useMemo(() => {
      if (!highlightedEdgeIds) {
        return edges;
      }
      return edges.map((edge) => {
        const isInPath = highlightedEdgeIds.has(edge.id);
        return {
          ...edge,
          animated: isInPath || edge.animated,
          style: {
            ...edge.style,
            stroke: isInPath ? '#38bdf8' : edge.style?.stroke,
            strokeWidth: isInPath ? 3 : edge.style?.strokeWidth,
            opacity: isInPath ? 1 : 0.25,
          },
        };
      });
    }, [edges, highlightedEdgeIds]);

    const handleNodeClick = useCallback(
      (event: React.MouseEvent, node: Node) => {
        // Support both desktop Shift+Click and multi-selection mode for mobile/touch
        if (event.shiftKey || (selectedNodeId && selectedNodeId !== node.id && !targetNodeId)) {
          if (!selectedNodeId) {
            setSelectedNodeId(node.id);
          } else if (selectedNodeId === node.id) {
            setSelectedNodeId(null);
            setTargetNodeId(null);
          } else {
            setTargetNodeId((prev) => (prev === node.id ? null : node.id));
          }
        } else {
          // Normal Click / First Selection: Single-node dependency graph tracing
          if (targetNodeId) {
            setTargetNodeId(null);
          }
          setSelectedNodeId((prev) => (prev === node.id ? null : node.id));
        }
      },
      [selectedNodeId, targetNodeId],
    );

    const handlePaneClick = useCallback(() => {
      setSelectedNodeId(null);
      setTargetNodeId(null);
    }, []);

    const handleCopyJson = async () => {
      if (!activeIR) {
        return;
      }
      try {
        await navigator.clipboard.writeText(JSON.stringify(activeIR, null, 2));
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
        toast({ title: 'JSON Copied', description: 'Architecture IR copied to clipboard' });
      } catch (e) {
        toast({ variant: 'destructive', title: 'Copy Failed', description: String(e) });
      }
    };

    const handleExportSvg = () => {
      if (!containerRef.current) {
        return;
      }
      try {
        const viewportEl = containerRef.current.querySelector('.react-flow__viewport') as HTMLElement | null;
        if (!viewportEl) {
          toast({ variant: 'destructive', title: 'Export Failed', description: 'Viewport element not found' });
          return;
        }

        // Inline relevant styles into the clone to guarantee standalone SVG rendering
        const clone = viewportEl.cloneNode(true) as HTMLElement;
        const styles = Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
          .map((s) => s.outerHTML)
          .join('\n');

        const svgData = `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000">
          <foreignObject width="100%" height="100%">
            <div xmlns="http://www.w3.org/1999/xhtml">
              ${styles}
              <div class="${document.documentElement.className}">
                ${clone.innerHTML}
              </div>
            </div>
          </foreignObject>
        </svg>`;

        const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.download = `${activeIR?.title || 'architecture-diagram'}.svg`;
        link.href = url;
        link.click();
        URL.revokeObjectURL(url);
        toast({ title: 'Export Successful', description: 'Architecture diagram exported as standalone SVG' });
      } catch (e) {
        toast({ variant: 'destructive', title: 'Export Failed', description: String(e) });
      }
    };

    const handleExportPng = async () => {
      if (!containerRef.current) {
        return;
      }
      try {
        const isDark = document.documentElement.classList.contains('dark');

        // Target the ReactFlow viewportpane which contains all nodes and edges
        const viewportEl = containerRef.current.querySelector('.react-flow__viewport') as HTMLElement | null;
        const targetEl = viewportEl || containerRef.current;

        const canvas = await html2canvas(targetEl, {
          backgroundColor: isDark ? '#020617' : '#ffffff',
          scale: 2,
          useCORS: true,
          logging: false,
          ignoreElements: (el) => {
            // Exclude controls, minimap, overlays from the diagram export
            return (
              el.classList.contains('react-flow__controls') ||
              el.classList.contains('react-flow__minimap') ||
              el.classList.contains('react-flow__background')
            );
          },
        });
        const url = canvas.toDataURL('image/png');
        const link = document.createElement('a');
        link.download = `${activeIR?.title || 'architecture-diagram'}.png`;
        link.href = url;
        link.click();
        toast({ title: 'Export Successful', description: 'Architecture diagram exported as high-res PNG' });
      } catch (e) {
        toast({ variant: 'destructive', title: 'Export Failed', description: String(e) });
      }
    };

    if (!activeIR) {
      // Dual-track fallback: check if content looks like Mermaid DSL
      if (
        content &&
        (content.includes('graph ') ||
          content.includes('flowchart ') ||
          content.includes('sequenceDiagram') ||
          content.includes('classDiagram'))
      ) {
        return (
          <div className="h-full w-full overflow-auto p-4">
            <MermaidPreview content={content} />
          </div>
        );
      }
      return (
        <div className="flex h-full w-full items-center justify-center p-6 text-muted-foreground text-sm">
          Invalid architecture JSON schema or failed to parse.
        </div>
      );
    }

    return (
      <div className="relative flex h-full w-full flex-col bg-background select-none overflow-hidden">
        {/* Header Toolbar */}
        <div className="z-10 flex flex-wrap items-center justify-between gap-2 border-b bg-muted/40 px-4 py-2 text-xs">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-foreground text-sm truncate max-w-[200px] sm:max-w-xs">
              {activeIR.title || 'System Architecture Map'}
            </h3>
            {activeIR.type && (
              <Badge variant="outline" className="text-[10px] uppercase font-mono">
                {activeIR.type}
              </Badge>
            )}
            {isDiffMode && (
              <Badge className="bg-amber-500 hover:bg-amber-600 text-white text-[10px]">Evolution Diff Active</Badge>
            )}
            {diffSummary && (
              <div className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-background border shadow-2xs">
                {diffSummary.addedNodes > 0 && (
                  <span className="text-emerald-600 dark:text-emerald-400">+{diffSummary.addedNodes} Nodes</span>
                )}
                {diffSummary.deletedNodes > 0 && (
                  <span className="text-rose-600 dark:text-rose-400">-{diffSummary.deletedNodes} Nodes</span>
                )}
                {diffSummary.modifiedNodes > 0 && (
                  <span className="text-amber-600 dark:text-amber-400">~{diffSummary.modifiedNodes} Modified</span>
                )}
                {diffSummary.addedEdges > 0 && (
                  <span className="text-cyan-600 dark:text-cyan-400">+{diffSummary.addedEdges} Edges</span>
                )}
                {diffSummary.deletedEdges > 0 && (
                  <span className="text-rose-500">-{diffSummary.deletedEdges} Edges</span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Search filter */}
            <div className="relative w-36 sm:w-48">
              <Search className="absolute left-2 top-2 text-muted-foreground" size={13} />
              <Input
                placeholder="Search nodes..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-7 pl-7 text-xs bg-background"
              />
            </div>

            {/* Diff Toggle */}
            {previousIR && (
              <Button
                variant={isDiffMode ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs gap-1"
                onClick={() => setIsDiffMode(!isDiffMode)}
              >
                <GitCompare size={12} />
                {isDiffMode ? 'Live View' : 'Diff View'}
              </Button>
            )}

            {/* Copy JSON Button */}
            <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={handleCopyJson}>
              {isCopied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
              {isCopied ? 'Copied' : 'JSON'}
            </Button>

            {/* Export SVG Button */}
            <Button variant="outline" size="sm" className="h-7 text-xs gap-1 hidden sm:flex" onClick={handleExportSvg}>
              <Download size={12} />
              SVG
            </Button>

            {/* Export PNG Button */}
            <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={handleExportPng}>
              <Download size={12} />
              PNG
            </Button>
          </div>
        </div>

        {/* Canvas Area */}
        <div ref={containerRef} className="relative flex-1 w-full h-full">
          <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            onNodeClick={handleNodeClick}
            onPaneClick={handlePaneClick}
            fitView
            minZoom={0.2}
            maxZoom={2.5}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls className="!bg-background !border !shadow-sm !rounded-md" />
            <MiniMap
              className="!bg-background/80 !border !rounded-md !overflow-hidden hidden sm:block"
              nodeStrokeWidth={3}
              zoomable
              pannable
            />
          </ReactFlow>

          {/* Quick Info Overlay at bottom */}
          {selectedNodeId && (
            <div className="absolute bottom-4 left-4 z-10 flex items-center gap-2 rounded-md border bg-background/90 px-3 py-1.5 shadow-md backdrop-blur-xs text-xs">
              {targetNodeId ? (
                <>
                  <Route size={13} className="text-cyan-500" />
                  <span>
                    Shortest Path: <strong>{selectedNodeId}</strong> → <strong>{targetNodeId}</strong>
                    {shortestPathResult?.found && (
                      <span className="ml-1 text-muted-foreground font-mono text-[10px]">
                        ({shortestPathResult.nodeIds.length - 1} hops)
                      </span>
                    )}
                    {!shortestPathResult?.found && (
                      <span className="ml-1 text-rose-500 font-medium text-[10px]">(no directed path)</span>
                    )}
                  </span>
                </>
              ) : (
                <>
                  <Eye size={13} className="text-primary" />
                  <span>
                    Tracing dependency tree for: <strong>{selectedNodeId}</strong>
                    <span className="ml-1 text-muted-foreground text-[10px] hidden sm:inline">
                      (Click another node to trace route)
                    </span>
                  </span>
                </>
              )}
              <button
                type="button"
                onClick={() => {
                  setSelectedNodeId(null);
                  setTargetNodeId(null);
                }}
                className="ml-2 text-muted-foreground hover:text-foreground text-[10px] underline"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </div>
    );
  },
);

ArchitecturePreview.displayName = 'ArchitecturePreview';
export default ArchitecturePreview;
