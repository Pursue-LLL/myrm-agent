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
import { Search, Download, GitCompare, RefreshCw, ZoomIn, Eye } from 'lucide-react';
import type { ArchitectureIR } from './types';
import { computeDagreLayout, sanitizeArchitectureIR } from './layout';
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
}

export const ArchitecturePreview: React.FC<ArchitecturePreviewProps> = memo(
  ({ content, versions, viewingVersionIndex = -1 }) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [isDiffMode, setIsDiffMode] = useState(false);
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

    const [nodes, setNodes, onNodesChange] = useNodesState(initialElements.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialElements.edges);

    // Sync layout when activeIR changes
    React.useEffect(() => {
      setNodes(initialElements.nodes);
      setEdges(initialElements.edges);
    }, [initialElements, setNodes, setEdges]);

    // Calculate highlighted upstream and downstream nodes when selectedNodeId is active
    const connectedNodeIds = useMemo(() => {
      if (!selectedNodeId || !activeIR) {
        return null;
      }
      const set = new Set<string>([selectedNodeId]);
      for (const edge of activeIR.edges) {
        if (edge.source === selectedNodeId) {
          set.add(edge.target);
        }
        if (edge.target === selectedNodeId) {
          set.add(edge.source);
        }
      }
      return set;
    }, [selectedNodeId, activeIR]);

    // Update node states based on search and connected path tracing
    const displayNodes = useMemo(() => {
      const query = searchQuery.trim().toLowerCase();
      return nodes.map((node) => {
        const label = String(node.data?.label || '').toLowerCase();
        const matchesSearch = query ? label.includes(query) : true;
        const isConnected = connectedNodeIds ? connectedNodeIds.has(node.id) : true;

        return {
          ...node,
          data: {
            ...node.data,
            isHighlighted: node.id === selectedNodeId,
            isDimmed: (!matchesSearch || !isConnected) && Boolean(query || selectedNodeId),
          },
        };
      });
    }, [nodes, searchQuery, selectedNodeId, connectedNodeIds]);

    const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
      setSelectedNodeId((prev) => (prev === node.id ? null : node.id));
    }, []);

    const handlePaneClick = useCallback(() => {
      setSelectedNodeId(null);
    }, []);

    const handleExportPng = async () => {
      if (!containerRef.current) {
        return;
      }
      try {
        const canvas = await html2canvas(containerRef.current, {
          backgroundColor: '#020617',
          scale: 2,
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
      if (content && (content.includes('graph ') || content.includes('flowchart ') || content.includes('sequenceDiagram') || content.includes('classDiagram'))) {
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
              <Badge className="bg-amber-500 hover:bg-amber-600 text-white text-[10px]">
                Evolution Diff Active
              </Badge>
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

            {/* Export Button */}
            <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={handleExportPng}>
              <Download size={12} />
              Export
            </Button>
          </div>
        </div>

        {/* Canvas Area */}
        <div ref={containerRef} className="relative flex-1 w-full h-full">
          <ReactFlow
            nodes={displayNodes}
            edges={edges}
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
              <Eye size={13} className="text-primary" />
              <span>
                Tracing paths for: <strong>{selectedNodeId}</strong>
              </span>
              <button
                type="button"
                onClick={() => setSelectedNodeId(null)}
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
