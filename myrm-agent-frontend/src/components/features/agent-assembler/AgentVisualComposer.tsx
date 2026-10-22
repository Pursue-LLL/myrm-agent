'use client';

/**
 * Visual Modular Agent Assembler Top-Level Workbench Component.
 *
 * [INPUT] initialBlueprint?: AssemblyBlueprint, onSaveBlueprint?: (bp: AssemblyBlueprint) => void
 * [OUTPUT] AgentVisualComposer: Complete three-pane block-based Lego-style capability composer.
 * [POS] src/components/features/agent-assembler/AgentVisualComposer.tsx
 */

import { memo, useState, useEffect, useCallback, useMemo } from 'react';
import {
  Boxes,
  Save,
  Download,
  RotateCcw,
  Sparkles,
  LayoutGrid,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  AssemblyBlueprint,
  AssemblyValidationResult,
  CapabilityBlock,
  SandboxDryRunResult,
  PresetTemplateKey,
} from './assemblerTypes';
import { assemblerService, DEFAULT_BLOCK_CATALOG } from './assemblerService';
import { AssemblerBlockCatalog } from './AssemblerBlockCatalog';
import { AssemblerCanvas } from './AssemblerCanvas';
import { AssemblerDryRunPlayground } from './AssemblerDryRunPlayground';

export interface AgentVisualComposerProps {
  initialBlueprint?: AssemblyBlueprint;
  onSaveBlueprint?: (blueprint: AssemblyBlueprint) => void;
  className?: string;
}

const PRESET_TEMPLATES: Record<PresetTemplateKey, { name: string; description: string; blockIds: string[] }> = {
  architect: {
    name: 'Full-Stack Software Architect',
    description: 'Autonomous engineering lead with tools, sandbox, and strict linting rules.',
    blockIds: ['brain-sonnet', 'persona-engineer', 'tools-core-dev', 'sandbox-strict'],
  },
  analyst: {
    name: 'Deep Research & Data Analyst',
    description: 'Evidence-driven researcher equipped with web search skills and semantic memory.',
    blockIds: ['brain-gpt4o', 'persona-analyst', 'memory-hierarchical', 'skills-github-ci'],
  },
  general: {
    name: 'Agile Executive Assistant',
    description: 'Balanced reasoning agent capable of diverse everyday coordination.',
    blockIds: ['brain-sonnet', 'persona-engineer'],
  },
};

export const AgentVisualComposer = memo(function AgentVisualComposer({
  initialBlueprint,
  onSaveBlueprint,
  className,
}: AgentVisualComposerProps) {
  const t = useTranslations('agentAssembler');

  const [catalog, setCatalog] = useState<CapabilityBlock[]>(DEFAULT_BLOCK_CATALOG);
  const [blueprint, setBlueprint] = useState<AssemblyBlueprint>(() => {
    if (initialBlueprint) {
      return initialBlueprint;
    }
    const preset = PRESET_TEMPLATES.architect;
    const blocks = DEFAULT_BLOCK_CATALOG.filter((b) => preset.blockIds.includes(b.id));
    return {
      name: preset.name,
      description: preset.description,
      blocks,
    };
  });

  const [validation, setValidation] = useState<AssemblyValidationResult | null>(null);

  // Fetch remote catalog
  useEffect(() => {
    let active = true;
    void assemblerService.getBlockCatalog().then((data) => {
      if (active && data.length > 0) {
        setCatalog(data);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  // Live validate on blueprint modifications
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      void assemblerService.validateAssembly(blueprint).then((res) => {
        if (active) {
          setValidation(res);
        }
      });
    }, 150);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [blueprint]);

  const equippedBlockIds = useMemo(() => {
    return blueprint.blocks.map((b) => b.id);
  }, [blueprint.blocks]);

  const handleUpdateName = useCallback((name: string) => {
    setBlueprint((prev) => ({ ...prev, name }));
  }, []);

  const handleUpdateDescription = useCallback((description: string) => {
    setBlueprint((prev) => ({ ...prev, description }));
  }, []);

  const handleAddBlock = useCallback((block: CapabilityBlock) => {
    setBlueprint((prev) => {
      if (prev.blocks.some((b) => b.id === block.id)) {
        return prev;
      }
      return { ...prev, blocks: [...prev.blocks, { ...block, enabled: true }] };
    });
  }, []);

  const handleToggleBlock = useCallback((id: string) => {
    setBlueprint((prev) => ({
      ...prev,
      blocks: prev.blocks.map((b) => {
        if (b.id === id) {
          return { ...b, enabled: !b.enabled };
        }
        return b;
      }),
    }));
  }, []);

  const handleRemoveBlock = useCallback((id: string) => {
    setBlueprint((prev) => ({
      ...prev,
      blocks: prev.blocks.filter((b) => b.id !== id),
    }));
  }, []);

  const handleUpdateConfig = useCallback((id: string, config: CapabilityBlock['config']) => {
    setBlueprint((prev) => ({
      ...prev,
      blocks: prev.blocks.map((b) => {
        if (b.id === id) {
          return { ...b, config: { ...b.config, ...config } };
        }
        return b;
      }),
    }));
  }, []);

  const handleApplyPreset = useCallback((key: PresetTemplateKey) => {
    const preset = PRESET_TEMPLATES[key];
    const newBlocks = catalog.filter((b) => preset.blockIds.includes(b.id));
    setBlueprint({
      name: preset.name,
      description: preset.description,
      blocks: newBlocks,
    });
  }, [catalog]);

  const handleDryRun = useCallback(async (prompt: string): Promise<SandboxDryRunResult | null> => {
    return assemblerService.dryRunAssembly({
      blueprint,
      prompt,
    });
  }, [blueprint]);

  const handleExportJson = useCallback(() => {
    const jsonStr = JSON.stringify(blueprint, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${(blueprint.name || 'agent-blueprint').toLowerCase().replace(/\s+/g, '-')}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }, [blueprint]);

  const handleSave = useCallback(() => {
    if (onSaveBlueprint) {
      onSaveBlueprint(blueprint);
    }
  }, [onSaveBlueprint, blueprint]);

  return (
    <div
      className={cn(
        'flex flex-col h-full w-full bg-background text-foreground select-text',
        className,
      )}
      data-testid="agent-visual-composer"
    >
      {/* Top Action Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/80 bg-muted/20 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <Boxes className="h-5 w-5 text-primary" />
          <div className="flex flex-col">
            <span className="font-bold text-xs">
              {t('composerTitle') || 'Visual Modular Agent Assembler'}
            </span>
            <span className="text-[10px] text-muted-foreground">
              {t('composerSubtitle') || 'Block-Based Capability Composer & Sandbox Testbed'}
            </span>
          </div>
        </div>

        {/* Preset Buttons & Action CTAs */}
        <div className="flex items-center gap-1.5">
          <div className="hidden md:flex items-center gap-1 mr-2 bg-muted/40 p-0.5 rounded-lg border border-border/60">
            <span className="text-[10px] px-1.5 text-muted-foreground font-medium flex items-center gap-1">
              <Sparkles className="h-3 w-3 text-amber-500" />
              {t('presets') || 'Presets:'}
            </span>
            <button
              type="button"
              onClick={() => {
                handleApplyPreset('architect');
              }}
              className="px-2 py-0.5 rounded text-[10px] hover:bg-muted text-foreground transition-colors"
            >
              Architect
            </button>
            <button
              type="button"
              onClick={() => {
                handleApplyPreset('analyst');
              }}
              className="px-2 py-0.5 rounded text-[10px] hover:bg-muted text-foreground transition-colors"
            >
              Analyst
            </button>
            <button
              type="button"
              onClick={() => {
                handleApplyPreset('general');
              }}
              className="px-2 py-0.5 rounded text-[10px] hover:bg-muted text-foreground transition-colors"
            >
              General
            </button>
          </div>

          <button
            type="button"
            onClick={handleExportJson}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs border border-border/80 bg-card hover:bg-muted text-foreground transition-colors"
            title={t('exportJson') || 'Export Blueprint JSON'}
          >
            <Download className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="hidden sm:inline">{t('export') || 'Export'}</span>
          </button>

          {onSaveBlueprint && (
            <button
              type="button"
              onClick={handleSave}
              className="flex items-center gap-1 px-3 py-1 rounded-md text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs transition-all"
            >
              <Save className="h-3.5 w-3.5" />
              <span>{t('saveBlueprint') || 'Save Agent'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Three-Pane Workbench Grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-3 p-3 overflow-hidden">
        {/* Pane 1: Left Building Blocks Catalog (col-span-3) */}
        <div className="lg:col-span-3 h-full overflow-hidden">
          <AssemblerBlockCatalog
            catalog={catalog}
            equippedBlockIds={equippedBlockIds}
            onAddBlock={handleAddBlock}
          />
        </div>

        {/* Pane 2: Middle Assembly Canvas (col-span-5) */}
        <div className="lg:col-span-5 h-full overflow-hidden">
          <AssemblerCanvas
            blueprint={blueprint}
            validation={validation}
            onUpdateName={handleUpdateName}
            onUpdateDescription={handleUpdateDescription}
            onToggleBlock={handleToggleBlock}
            onRemoveBlock={handleRemoveBlock}
            onUpdateConfig={handleUpdateConfig}
          />
        </div>

        {/* Pane 3: Right Live Sandbox Testbed & Dry-Run (col-span-4) */}
        <div className="lg:col-span-4 h-full overflow-hidden">
          <AssemblerDryRunPlayground
            blueprint={blueprint}
            onDryRun={handleDryRun}
          />
        </div>
      </div>
    </div>
  );
});
