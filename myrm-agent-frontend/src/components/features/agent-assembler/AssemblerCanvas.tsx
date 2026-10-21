'use client';

/**
 * Assembler Canvas Component for Visual Modular Agent Assembler.
 *
 * [INPUT] blueprint: AssemblyBlueprint, validation: AssemblyValidationResult | null, onUpdateName, onUpdateDescription, onToggleBlock, onRemoveBlock, onUpdateConfig
 * [OUTPUT] AssemblerCanvas: Visual interactive assembly canvas with live dependency health check banner.
 * [POS] src/components/features/agent-assembler/AssemblerCanvas.tsx
 */

import { memo, useState } from 'react';
import {
  Boxes,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Lightbulb,
  ChevronDown,
  Layers,
  Sparkles,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  AssemblyBlueprint,
  AssemblyValidationResult,
  CapabilityBlock,
} from './assemblerTypes';
import { CapabilityBlockCard } from './CapabilityBlockCard';

export interface AssemblerCanvasProps {
  blueprint: AssemblyBlueprint;
  validation: AssemblyValidationResult | null;
  onUpdateName: (name: string) => void;
  onUpdateDescription: (description: string) => void;
  onToggleBlock: (id: string) => void;
  onRemoveBlock: (id: string) => void;
  onUpdateConfig: (id: string, config: CapabilityBlock['config']) => void;
  className?: string;
}

export const AssemblerCanvas = memo(function AssemblerCanvas({
  blueprint,
  validation,
  onUpdateName,
  onUpdateDescription,
  onToggleBlock,
  onRemoveBlock,
  onUpdateConfig,
  className,
}: AssemblerCanvasProps) {
  const t = useTranslations('agentAssembler');
  const [showDetails, setShowDetails] = useState(false);

  const activeCount = blueprint.blocks.filter((b) => b.enabled).length;

  return (
    <div
      className={cn(
        'flex flex-col h-full rounded-xl border border-border bg-card/40 backdrop-blur-sm overflow-hidden',
        className,
      )}
      data-testid="assembler-canvas"
    >
      {/* Top Header: Name & Description Inputs */}
      <div className="p-3.5 border-b border-border/60 bg-muted/20 flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Boxes className="h-4 w-4 text-primary" />
          <input
            type="text"
            value={blueprint.name}
            onChange={(e) => {
              onUpdateName(e.target.value);
            }}
            placeholder={t('agentNamePlaceholder') || 'Agent Blueprint Name (e.g. Full-Stack Lead)'}
            className="flex-1 font-semibold text-sm bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none px-1 text-foreground placeholder:text-muted-foreground"
          />
        </div>
        <input
          type="text"
          value={blueprint.description}
          onChange={(e) => {
            onUpdateDescription(e.target.value);
          }}
          placeholder={t('agentDescPlaceholder') || 'Enter concise purpose and operational scope...'}
          className="text-xs bg-transparent border-b border-transparent hover:border-border focus:border-primary/60 focus:outline-none px-1 text-muted-foreground"
        />
      </div>

      {/* Validation Health Banner */}
      {validation && (
        <div className="border-b border-border/60 bg-muted/30 px-3.5 py-2 flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {validation.is_valid ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              ) : (
                <AlertCircle className="h-4 w-4 text-rose-500" />
              )}
              <span className="text-xs font-semibold text-foreground">
                {validation.is_valid
                  ? t('blueprintValid') || 'Blueprint Structurally Valid'
                  : t('blueprintInvalid') || 'Dependency Issues Detected'}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono text-muted-foreground">
                ~{validation.estimated_token_cost} tok
              </span>
            </div>

            {(validation.errors.length > 0 ||
              validation.warnings.length > 0 ||
              validation.suggestions.length > 0) && (
              <button
                type="button"
                onClick={() => {
                  setShowDetails((prev) => !prev);
                }}
                className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              >
                <span>{showDetails ? t('hideReport') || 'Hide' : t('viewReport') || 'Report'}</span>
                <ChevronDown
                  className={cn(
                    'h-3 w-3 transition-transform duration-150',
                    showDetails && 'rotate-180',
                  )}
                />
              </button>
            )}
          </div>

          {/* Collapsible Issues & Suggestions Report */}
          {showDetails && (
            <div className="mt-1 pt-1.5 border-t border-border/40 flex flex-col gap-1.5 text-[11px]">
              {validation.errors.map((err, idx) => (
                <div key={`err-${idx}`} className="flex items-start gap-1.5 text-rose-600 dark:text-rose-400">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                  <span>{err}</span>
                </div>
              ))}
              {validation.warnings.map((warn, idx) => (
                <div key={`warn-${idx}`} className="flex items-start gap-1.5 text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                  <span>{warn}</span>
                </div>
              ))}
              {validation.suggestions.map((sug, idx) => (
                <div key={`sug-${idx}`} className="flex items-start gap-1.5 text-sky-600 dark:text-sky-400">
                  <Lightbulb className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                  <span>{sug}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Canvas Block Assembly Area */}
      <div className="flex-1 overflow-y-auto p-3.5 flex flex-col gap-2.5">
        <div className="flex items-center justify-between text-xs text-muted-foreground px-0.5">
          <div className="flex items-center gap-1.5">
            <Layers className="h-3.5 w-3.5" />
            <span>{t('assembledBlocks') || 'Equipped Capability Blocks'}</span>
          </div>
          <span className="font-mono text-[11px]">
            {activeCount}/{blueprint.blocks.length} {t('active') || 'active'}
          </span>
        </div>

        {blueprint.blocks.length > 0 ? (
          blueprint.blocks.map((block) => (
            <CapabilityBlockCard
              key={block.id}
              block={block}
              onToggle={onToggleBlock}
              onRemove={onRemoveBlock}
              onUpdateConfig={onUpdateConfig}
            />
          ))
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center border-2 border-dashed border-border/60 rounded-xl my-4">
            <Sparkles className="h-8 w-8 text-muted-foreground/40 mb-2" />
            <span className="font-medium text-xs text-foreground">
              {t('emptyCanvasTitle') || 'Assembly Canvas is Empty'}
            </span>
            <p className="text-[11px] text-muted-foreground mt-1 max-w-xs">
              {t('emptyCanvasDesc') || 'Equip capability blocks from the left pool or apply a starter preset to begin assembling your autonomous agent.'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
});
