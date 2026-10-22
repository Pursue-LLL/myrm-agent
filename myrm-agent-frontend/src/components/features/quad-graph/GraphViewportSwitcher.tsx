/**
 * [INPUT]
 * - quadGraphTypes: GraphViewportSwitcherProps, GraphLayerType
 *
 * [OUTPUT]
 * - GraphViewportSwitcher: Quad-layer view switcher tab bar with node count badges
 *
 * [POS]
 * Viewport Switcher for QuadGraphMultiLayerExecutionCanvasAndTopologyInspectionHUD (Item 50 P0).
 * Strictly under 160 lines. Zero `any`.
 */

'use client';

import React, { memo } from 'react';
import {
  Network,
  GitBranch,
  Users2,
  Radio,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { GraphLayerType, GraphViewportSwitcherProps } from './quadGraphTypes';

interface LayerOption {
  key: GraphLayerType;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
}

const LAYER_OPTIONS: LayerOption[] = [
  { key: 'task', labelKey: 'layerTask', icon: Network },
  { key: 'workflow', labelKey: 'layerWorkflow', icon: GitBranch },
  { key: 'team', labelKey: 'layerTeam', icon: Users2 },
  { key: 'communication', labelKey: 'layerCommunication', icon: Radio },
];

export const GraphViewportSwitcher: React.FC<GraphViewportSwitcherProps> = memo(({
  activeLayer,
  onSelectLayer,
  nodeCountsByLayer = { task: 0, workflow: 0, team: 0, communication: 0 },
  className = '',
}) => {
  const t = useTranslations('quadGraph');

  return (
    <nav
      data-testid="graph-viewport-switcher-root"
      aria-label={t('viewportSwitcherAria')}
      className={`inline-flex items-center p-1 bg-slate-900/90 dark:bg-slate-950/90 border border-slate-800 rounded-xl shadow-lg backdrop-blur-md gap-1 ${className}`}
    >
      {LAYER_OPTIONS.map((opt) => {
        const isActive = activeLayer === opt.key;
        const IconComponent = opt.icon;
        const count = nodeCountsByLayer[opt.key] || 0;

        return (
          <button
            key={opt.key}
            type="button"
            data-testid={`viewport-layer-btn-${opt.key}`}
            onClick={() => {
              onSelectLayer(opt.key);
            }}
            className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              isActive
                ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <IconComponent className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-slate-400'}`} />
            <span>{t(opt.labelKey)}</span>
            {count > 0 && (
              <span
                data-testid={`layer-count-${opt.key}`}
                className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold ${
                  isActive ? 'bg-blue-500/40 text-blue-100' : 'bg-slate-800 text-slate-400'
                }`}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
});

GraphViewportSwitcher.displayName = 'GraphViewportSwitcher';
