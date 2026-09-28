'use client';

import React, { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconShieldCheck,
  IconShieldAlert,
  IconBan,
  IconShield,
  IconZap,
  IconSliders,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { PermissionAction } from '@/services/config/types';
import {
  CAPABILITY_SURFACES,
  CAPABILITY_PRESETS,
  type CapabilitySurfaceKey,
  type CapabilityMatrix,
} from './securityPolicyUtils';

interface CapabilitySurfaceMatrixGridProps {
  matrix: CapabilityMatrix;
  onChange: (surfaceKey: CapabilitySurfaceKey, action: PermissionAction) => void;
  onApplyPreset: (matrix: CapabilityMatrix) => void;
}

export const CapabilitySurfaceMatrixGrid = memo<CapabilitySurfaceMatrixGridProps>(
  ({ matrix, onChange, onApplyPreset }) => {
    const t = useTranslations('settings.securityPolicy');

    const handleActionSelect = useCallback(
      (surfaceKey: CapabilitySurfaceKey, action: PermissionAction) => {
        onChange(surfaceKey, action);
      },
      [onChange],
    );

    return (
      <div className="space-y-4">
        {/* 预设模板快捷切换栏 */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3 rounded-lg border border-border/70 bg-muted/20">
          <div className="flex items-center gap-2">
            <IconSliders className="h-4 w-4 text-primary shrink-0" />
            <div>
              <p className="text-xs font-semibold text-foreground">
                {t('matrixPresets.title', { default: 'Capability Baseline Presets' })}
              </p>
              <p className="text-[11px] text-muted-foreground">
                {t('matrixPresets.desc', {
                  default: 'Quickly set fine-grained Always/Ask/Deny tri-state posture across all 6 core surfaces.',
                })}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
            {CAPABILITY_PRESETS.map((preset) => {
              const isMatch = Object.entries(preset.matrix).every(
                ([key, val]) => matrix[key as CapabilitySurfaceKey] === val,
              );
              return (
                <Button
                  key={preset.id}
                  data-testid={`capability-preset-${preset.id}`}
                  variant={isMatch ? 'secondary' : 'outline'}
                  size="sm"
                  className={`h-7 px-2.5 text-xs transition-all ${
                    isMatch ? 'border-primary/50 text-foreground font-medium shadow-xs' : 'text-muted-foreground'
                  }`}
                  onClick={() => onApplyPreset(preset.matrix)}
                  title={preset.description}
                >
                  {preset.id === 'guarded' && <IconShield className="h-3 w-3 mr-1 text-emerald-500" />}
                  {preset.id === 'balanced' && <IconShieldCheck className="h-3 w-3 mr-1 text-primary" />}
                  {preset.id === 'geek' && <IconZap className="h-3 w-3 mr-1 text-amber-500" />}
                  {preset.name}
                </Button>
              );
            })}
          </div>
        </div>

        {/* 6 大能力面网格 */}
        <div data-testid="capability-matrix-grid" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {CAPABILITY_SURFACES.map((surface) => {
            const currentAction = matrix[surface.key] ?? surface.defaultAction;

            return (
              <div
                key={surface.key}
                data-testid={`capability-surface-card-${surface.key}`}
                className={`flex flex-col justify-between p-3.5 rounded-lg border transition-all duration-150 ${
                  currentAction === 'allow'
                    ? 'border-emerald-500/30 bg-emerald-500/[0.02]'
                    : currentAction === 'ask'
                      ? 'border-amber-500/30 bg-amber-500/[0.02]'
                      : 'border-destructive/30 bg-destructive/[0.02]'
                }`}
              >
                <div className="space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <h4 className="text-xs font-semibold text-foreground tracking-tight leading-snug">
                      {surface.label}
                    </h4>
                    <Badge
                      variant="outline"
                      className={`text-[10px] px-1.5 py-0 uppercase shrink-0 font-mono ${
                        currentAction === 'allow'
                          ? 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                          : currentAction === 'ask'
                            ? 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10'
                            : 'border-destructive/40 text-destructive bg-destructive/10'
                      }`}
                    >
                      {currentAction}
                    </Badge>
                  </div>

                  <p className="text-[11px] text-muted-foreground leading-relaxed">{surface.description}</p>

                  <div className="flex flex-wrap gap-1 pt-1">
                    {surface.tools.map((tName) => (
                      <code
                        key={tName}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground font-mono"
                      >
                        {tName}
                      </code>
                    ))}
                  </div>
                </div>

                {/* 三态切换器 Segmented Controls */}
                <div className="pt-3 mt-2 border-t border-border/40 grid grid-cols-3 gap-1">
                  <button
                    type="button"
                    data-testid={`capability-action-${surface.key}-allow`}
                    onClick={() => handleActionSelect(surface.key, 'allow')}
                    className={`flex items-center justify-center gap-1 py-1 px-1.5 rounded text-xs font-medium transition-colors ${
                      currentAction === 'allow'
                        ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/40'
                        : 'text-muted-foreground hover:bg-muted/40'
                    }`}
                    title={t('modeAllow', { default: 'Always Allow without approval' })}
                  >
                    <IconShieldCheck className="h-3 w-3 shrink-0" />
                    <span>{t('modeAllowShort', { default: 'Allow' })}</span>
                  </button>

                  <button
                    type="button"
                    data-testid={`capability-action-${surface.key}-ask`}
                    onClick={() => handleActionSelect(surface.key, 'ask')}
                    className={`flex items-center justify-center gap-1 py-1 px-1.5 rounded text-xs font-medium transition-colors ${
                      currentAction === 'ask'
                        ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 ring-1 ring-amber-500/40'
                        : 'text-muted-foreground hover:bg-muted/40'
                    }`}
                    title={t('modeAsk', { default: 'Ask for confirmation before execution' })}
                  >
                    <IconShieldAlert className="h-3 w-3 shrink-0" />
                    <span>{t('modeAskShort', { default: 'Ask' })}</span>
                  </button>

                  <button
                    type="button"
                    data-testid={`capability-action-${surface.key}-deny`}
                    onClick={() => handleActionSelect(surface.key, 'deny')}
                    className={`flex items-center justify-center gap-1 py-1 px-1.5 rounded text-xs font-medium transition-colors ${
                      currentAction === 'deny'
                        ? 'bg-destructive/15 text-destructive ring-1 ring-destructive/40'
                        : 'text-muted-foreground hover:bg-muted/40'
                    }`}
                    title={t('modeDeny', { default: 'Strictly Deny execution' })}
                  >
                    <IconBan className="h-3 w-3 shrink-0" />
                    <span>{t('modeDenyShort', { default: 'Deny' })}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  },
);

CapabilitySurfaceMatrixGrid.displayName = 'CapabilitySurfaceMatrixGrid';
