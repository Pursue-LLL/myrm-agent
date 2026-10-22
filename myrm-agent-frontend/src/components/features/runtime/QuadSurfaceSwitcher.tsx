'use client';

/**
 * QuadSurfaceSwitcher Component.
 * Quick-switch bar between four primary Run projection surfaces:
 * Chat View | Runtime Console | Deliverables Board | Audit Ledger.
 * Zero-emoji design with accessible SVG icons.
 */

import React from 'react';
import { MessageSquare, PackageCheck, ShieldAlert, Terminal } from 'lucide-react';
import { SurfaceViewType } from './runtimeProjectionTypes';

interface QuadSurfaceSwitcherProps {
  activeSurface: SurfaceViewType;
  onSwitch: (surface: SurfaceViewType) => void;
}

interface SurfaceOption {
  key: SurfaceViewType;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const SURFACES: readonly SurfaceOption[] = [
  { key: 'chat', label: 'Chat View', icon: MessageSquare },
  { key: 'runtime_console', label: 'Runtime Console', icon: Terminal },
  { key: 'deliverables', label: 'Deliverables', icon: PackageCheck },
  { key: 'audit', label: 'Audit Ledger', icon: ShieldAlert },
] as const;

export const QuadSurfaceSwitcher: React.FC<QuadSurfaceSwitcherProps> = ({
  activeSurface,
  onSwitch,
}) => {
  return (
    <nav
      aria-label="Run Surface Switcher"
      className="flex items-center gap-1 p-1 bg-slate-900/90 border border-slate-800 rounded-lg shadow-inner text-xs font-medium"
    >
      {SURFACES.map((opt) => {
        const isActive = activeSurface === opt.key;
        const IconComponent = opt.icon;

        return (
          <button
            key={opt.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => {
              onSwitch(opt.key);
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all ${
              isActive
                ? 'bg-indigo-600 text-white shadow-sm font-semibold'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <IconComponent className="h-3.5 w-3.5 shrink-0" />
            <span>{opt.label}</span>
          </button>
        );
      })}
    </nav>
  );
};
