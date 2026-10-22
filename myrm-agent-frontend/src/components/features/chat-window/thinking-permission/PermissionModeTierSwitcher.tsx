'use client';

/**
 * [INPUT]
 * - thinkingPermissionTypes::PermissionTier, PERMISSION_TIER_CONFIGS (POS: Permission tier configs.)
 * - usePermissionTierStore::usePermissionTierStore (POS: Reactive permission mode store.)
 * - lucide-react::ShieldCheck, Zap, Rocket, ChevronDown, Check (POS: Vector icons.)
 *
 * [OUTPUT]
 * - PermissionModeTierSwitcher: 3-tier capsule toggle for agent autonomy & security gates.
 *
 * [POS]
 * Embedded input toolbar switcher allowing users to dynamically switch between Strict
 * guardrails, Semi-Auto agile code execution, and Full-Auto sandbox autonomy.
 */

import React, { useState, useRef, useEffect } from 'react';
import { ShieldCheck, Zap, Rocket, ChevronDown, Check } from 'lucide-react';
import {
  type PermissionTier,
  PERMISSION_TIER_CONFIGS,
} from './thinkingPermissionTypes';
import { usePermissionTierStore } from './usePermissionTierStore';

export interface PermissionModeTierSwitcherProps {
  className?: string;
  disabled?: boolean;
}

export default function PermissionModeTierSwitcher({
  className = '',
  disabled = false,
}: PermissionModeTierSwitcherProps) {
  const currentTier = usePermissionTierStore((state) => state.tier);
  const setTier = usePermissionTierStore((state) => state.setTier);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentConfig = PERMISSION_TIER_CONFIGS[currentTier];

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownOpen]);

  const renderTierIcon = (tier: PermissionTier, iconClassName: string = 'w-3.5 h-3.5') => {
    if (tier === 'strict') {
      return <ShieldCheck className={iconClassName} aria-hidden="true" />;
    }
    if (tier === 'semi-auto') {
      return <Zap className={iconClassName} aria-hidden="true" />;
    }
    return <Rocket className={iconClassName} aria-hidden="true" />;
  };

  const handleTierSelect = (tier: PermissionTier) => {
    if (disabled) {
      return;
    }
    setTier(tier);
    setDropdownOpen(false);
  };

  return (
    <div
      ref={containerRef}
      data-testid="permission-mode-tier-switcher"
      className={`relative inline-flex items-center ${className}`}
    >
      {/* Main trigger capsule button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          if (!disabled) {
            setDropdownOpen((prev) => !prev);
          }
        }}
        data-testid="permission-tier-trigger"
        aria-expanded={dropdownOpen}
        aria-haspopup="true"
        className={`inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium rounded-md border transition-all ${
          currentConfig.borderColorClass
        } ${currentConfig.badgeBgClass} ${currentConfig.colorClass} hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed`}
        title={`当前权限：${currentConfig.shortLabel} · ${currentConfig.description}`}
      >
        {renderTierIcon(currentTier)}
        <span>{currentConfig.shortLabel}</span>
        <ChevronDown
          className={`w-3 h-3 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {/* Dropdown panel explaining each tier */}
      {dropdownOpen && (
        <div
          data-testid="permission-tier-menu"
          className="absolute bottom-full mb-1.5 left-0 z-50 w-64 rounded-lg border border-border/80 bg-popover/95 p-1.5 text-popover-foreground shadow-lg backdrop-blur-md animate-in fade-in-0 zoom-in-95"
        >
          <div className="px-2 py-1 border-b border-border/40 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            智能体权限控制模式
          </div>

          <div className="flex flex-col gap-1 mt-1">
            {(Object.keys(PERMISSION_TIER_CONFIGS) as PermissionTier[]).map((tierKey) => {
              const config = PERMISSION_TIER_CONFIGS[tierKey];
              const isSelected = tierKey === currentTier;

              return (
                <button
                  key={tierKey}
                  type="button"
                  data-testid={`permission-option-${tierKey}`}
                  onClick={() => {
                    handleTierSelect(tierKey);
                  }}
                  className={`w-full text-left flex items-start gap-2 p-2 rounded-md transition-colors ${
                    isSelected
                      ? 'bg-muted/80 text-foreground font-medium'
                      : 'hover:bg-muted/40 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <div className={`shrink-0 mt-0.5 ${config.colorClass}`}>
                    {renderTierIcon(tierKey, 'w-4 h-4')}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-foreground">{config.shortLabel}</span>
                      {isSelected && <Check className="w-3.5 h-3.5 text-primary" aria-hidden="true" />}
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                      {config.description}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
