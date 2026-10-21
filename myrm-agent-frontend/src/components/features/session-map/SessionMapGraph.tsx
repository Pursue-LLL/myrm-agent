'use client';

/**
 * [INPUT]
 * - ProjectCluster, SessionNode, AgentState from @/services/sessionMap
 * - User interaction events (click, zoom, filter)
 *
 * [OUTPUT]
 * - SessionMapGraph: 2D topological SVG canvas rendering project containers and agent pulse nodes
 *
 * [POS]
 * Visual 2D force/cluster layout topology map for Project-Centric Session Map and Fleet Cockpit View.
 * Strict typing: Zero `any`. File length < 380 lines. Zero native emoji.
 */

import { useState, useMemo, useCallback } from 'react';
import type { ProjectCluster, SessionNode, AgentState } from '@/services/sessionMap';

export interface SessionMapGraphProps {
  clusters: ProjectCluster[];
  selectedSessionId?: string;
  onSelectSession: (session: SessionNode, project: ProjectCluster) => void;
  stateFilter?: AgentState;
  searchQuery?: string;
}

interface NodePosition {
  session: SessionNode;
  project: ProjectCluster;
  x: number;
  y: number;
  isMatch: boolean;
}

interface ClusterGeometry {
  project: ProjectCluster;
  cx: number;
  cy: number;
  radius: number;
  nodes: NodePosition[];
}

const STATE_COLORS: Record<AgentState, { stroke: string; fill: string; ring: string }> = {
  working: {
    stroke: '#10b981',
    fill: '#059669',
    ring: 'rgba(16, 185, 129, 0.4)',
  },
  ready: {
    stroke: '#3b82f6',
    fill: '#2563eb',
    ring: 'rgba(59, 130, 246, 0.35)',
  },
  waiting_input: {
    stroke: '#f59e0b',
    fill: '#d97706',
    ring: 'rgba(245, 158, 11, 0.4)',
  },
  idle: {
    stroke: '#64748b',
    fill: '#475569',
    ring: 'rgba(100, 116, 139, 0.25)',
  },
  error: {
    stroke: '#ef4444',
    fill: '#dc2626',
    ring: 'rgba(239, 68, 68, 0.45)',
  },
};

export function SessionMapGraph({
  clusters,
  selectedSessionId,
  onSelectSession,
  stateFilter,
  searchQuery = '',
}: SessionMapGraphProps) {
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const cleanQuery = searchQuery.trim().toLowerCase();

  // Compute cluster and node geometry layout
  const geometries = useMemo<ClusterGeometry[]>(() => {
    if (!clusters || clusters.length === 0) {
      return [];
    }

    const cols = Math.max(1, Math.ceil(Math.sqrt(clusters.length)));
    const clusterSpacing = 360;

    return clusters.map((proj, cIdx) => {
      const col = cIdx % cols;
      const row = Math.floor(cIdx / cols);
      const cx = 220 + col * clusterSpacing;
      const cy = 200 + row * clusterSpacing;

      const filteredSessions = stateFilter
        ? proj.sessions.filter((s) => s.state === stateFilter)
        : proj.sessions;

      const nodeCount = filteredSessions.length;
      const radius = Math.max(120, 80 + nodeCount * 14);

      const nodes: NodePosition[] = filteredSessions.map((session, sIdx) => {
        // Arrange sessions in circular orbit around project center
        const angle = (sIdx / Math.max(1, nodeCount)) * 2 * Math.PI - Math.PI / 2;
        const orbitRadius = radius * 0.62;
        const nx = cx + Math.cos(angle) * orbitRadius;
        const ny = cy + Math.sin(angle) * orbitRadius;

        const isMatch = Boolean(
          cleanQuery &&
            (session.title.toLowerCase().includes(cleanQuery) ||
              session.agent_name.toLowerCase().includes(cleanQuery) ||
              (session.current_task && session.current_task.toLowerCase().includes(cleanQuery)) ||
              session.tags.some((t) => t.toLowerCase().includes(cleanQuery))),
        );

        return {
          session,
          project: proj,
          x: nx,
          y: ny,
          isMatch,
        };
      });

      return {
        project: proj,
        cx,
        cy,
        radius,
        nodes,
      };
    });
  }, [clusters, stateFilter, cleanQuery]);

  // Compute canvas viewBox boundary
  const { viewBoxWidth, viewBoxHeight } = useMemo(() => {
    if (geometries.length === 0) {
      return { viewBoxWidth: 800, viewBoxHeight: 600 };
    }
    const maxX = Math.max(...geometries.map((g) => g.cx + g.radius + 60));
    const maxY = Math.max(...geometries.map((g) => g.cy + g.radius + 60));
    return {
      viewBoxWidth: Math.max(800, maxX),
      viewBoxHeight: Math.max(600, maxY),
    };
  }, [geometries]);

  const handleZoomIn = useCallback(() => setZoomLevel((z) => Math.min(2.0, z + 0.15)), []);
  const handleZoomOut = useCallback(() => setZoomLevel((z) => Math.max(0.5, z - 0.15)), []);
  const handleResetZoom = useCallback(() => setZoomLevel(1.0), []);

  return (
    <div className="relative w-full h-[540px] rounded-2xl border border-border/80 bg-background/95 overflow-hidden select-none shadow-inner">
      {/* Zoom controls HUD */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-1.5 p-1 rounded-xl bg-card/90 border border-border/80 shadow-md backdrop-blur-md">
        <button
          type="button"
          onClick={handleZoomIn}
          className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold text-foreground hover:bg-muted transition-colors"
          title="Zoom in"
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={handleZoomOut}
          className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold text-foreground hover:bg-muted transition-colors"
          title="Zoom out"
          aria-label="Zoom out"
        >
          −
        </button>
        <button
          type="button"
          onClick={handleResetZoom}
          className="px-2 h-7 rounded-lg flex items-center justify-center text-[10px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          title="Reset zoom"
          aria-label="Reset zoom"
        >
          {Math.round(zoomLevel * 100)}%
        </button>
      </div>

      {/* SVG 2D Topology Canvas */}
      <svg
        className="w-full h-full cursor-grab active:cursor-grabbing transition-transform duration-100 ease-out"
        viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
        style={{
          transform: `scale(${zoomLevel})`,
          transformOrigin: 'center center',
        }}
      >
        <defs>
          <filter id="glow-effect" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Project Container Bubbles */}
        {geometries.map(({ project, cx, cy, radius }) => (
          <g key={project.id} className="transition-all duration-300">
            {/* Outer Project Glass Boundary */}
            <circle
              cx={cx}
              cy={cy}
              r={radius}
              fill="rgba(99, 102, 241, 0.03)"
              stroke={project.color || '#6366f1'}
              strokeWidth="1.5"
              strokeDasharray="4 4"
              className="opacity-70 hover:opacity-100 transition-opacity"
            />

            {/* Project Header Labels */}
            <text
              x={cx}
              y={cy - radius + 22}
              textAnchor="middle"
              className="text-xs font-semibold fill-foreground pointer-events-none select-none"
              style={{ fontSize: '13px', fontWeight: 600 }}
            >
              {project.name}
            </text>

            {project.workspace_path && (
              <text
                x={cx}
                y={cy - radius + 38}
                textAnchor="middle"
                className="text-[10px] font-mono fill-muted-foreground pointer-events-none select-none"
                style={{ fontSize: '10px' }}
              >
                {project.workspace_path}
              </text>
            )}
          </g>
        ))}

        {/* Connecting Lines between Project Center and Session Nodes */}
        {geometries.map(({ cx, cy, nodes }) =>
          nodes.map(({ session, x, y }) => (
            <line
              key={`line-${session.id}`}
              x1={cx}
              y1={cy}
              x2={x}
              y2={y}
              stroke="rgba(148, 163, 184, 0.2)"
              strokeWidth="1"
            />
          )),
        )}

        {/* Session Nodes */}
        {geometries.map(({ nodes }) =>
          nodes.map(({ session, project, x, y, isMatch }) => {
            const isSelected = selectedSessionId === session.id;
            const isHovered = hoveredNodeId === session.id;
            const colors = STATE_COLORS[session.state] || STATE_COLORS.ready;

            return (
              <g
                key={session.id}
                transform={`translate(${x}, ${y})`}
                className="cursor-pointer transition-transform duration-150 ease-out"
                onClick={() => onSelectSession(session, project)}
                onMouseEnter={() => setHoveredNodeId(session.id)}
                onMouseLeave={() => setHoveredNodeId(null)}
              >
                {/* Search Match or Selected Pulse Outer Ring */}
                {(isMatch || isSelected) && (
                  <circle
                    r={isSelected ? 22 : 20}
                    fill="none"
                    stroke={isSelected ? '#6366f1' : '#f59e0b'}
                    strokeWidth="2.5"
                    className="animate-pulse"
                    filter="url(#glow-effect)"
                  />
                )}

                {/* State Glow Ring */}
                <circle
                  r={isHovered ? 17 : 14}
                  fill={colors.ring}
                  className="transition-all duration-200"
                />

                {/* Main Node Body */}
                <circle
                  r={isHovered ? 13 : 11}
                  fill={colors.fill}
                  stroke="#ffffff"
                  strokeWidth="2"
                  className="shadow-md transition-all duration-200"
                />

                {/* Working Pulse Indicator Core */}
                {session.state === 'working' && (
                  <circle
                    r="4"
                    fill="#ffffff"
                    className="animate-ping opacity-75"
                  />
                )}

                {/* Session Node Title Badge */}
                <text
                  x="0"
                  y="24"
                  textAnchor="middle"
                  className="font-medium fill-foreground select-none pointer-events-none"
                  style={{
                    fontSize: isHovered || isSelected ? '11px' : '10px',
                    fontWeight: isSelected ? 700 : 500,
                  }}
                >
                  {session.title.length > 16
                    ? `${session.title.slice(0, 15)}…`
                    : session.title}
                </text>

                {/* Agent Name Tag */}
                <text
                  x="0"
                  y="36"
                  textAnchor="middle"
                  className="font-mono fill-muted-foreground select-none pointer-events-none"
                  style={{ fontSize: '9px' }}
                >
                  {session.agent_name}
                </text>
              </g>
            );
          }),
        )}
      </svg>
    </div>
  );
}
