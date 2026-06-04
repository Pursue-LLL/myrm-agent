'use client';

import { useState } from 'react';
import { IconAlertCircle, IconCheckCircle, IconChevronDown, IconChevronUp } from '@/components/features/icons/PremiumIcons';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { FullExportConfig } from '@/store/config/importExport';

export type ImportCategory =
  | 'systemInstructions'
  | 'generalSettings'
  | 'searchServices'
  | 'mcpServices'
  | 'providers'
  | 'defaultModel'
  | 'customModelInfo';

export interface ParsedImportData {
  version?: string;
  timestamp?: string;
  config: FullExportConfig;
  availableCategories: Set<ImportCategory>;
}

export function parseImportJson(json: string): ParsedImportData | { error: string } {
  try {
    const data = JSON.parse(json);
    if (!data.config) {
      return { error: 'invalidFormat' };
    }

    const config: FullExportConfig = data.config;
    const availableCategories = new Set<ImportCategory>();

    if (config.systemInstructions !== undefined) {
      availableCategories.add('systemInstructions');
    }
    if (
      config.fetchRawWebpage !== undefined ||
      config.extractDocumentText !== undefined ||
      config.generateSearchSuggestions !== undefined ||
      config.enableCostEstimation !== undefined
    ) {
      availableCategories.add('generalSettings');
    }
    if (config.searchServiceConfigs && config.searchServiceConfigs.length > 0) {
      availableCategories.add('searchServices');
    }
    if (config.mcpConfigs && config.mcpConfigs.length > 0) {
      availableCategories.add('mcpServices');
    }
    if (config.providers && config.providers.length > 0) {
      availableCategories.add('providers');
    }
    if (config.defaultModelConfig) {
      availableCategories.add('defaultModel');
    }
    if (config.customModelInfo && Object.keys(config.customModelInfo).length > 0) {
      availableCategories.add('customModelInfo');
    }

    return {
      version: data.version,
      timestamp: data.timestamp,
      config,
      availableCategories,
    };
  } catch {
    return { error: 'parseError' };
  }
}

interface ImportPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parsedData: ParsedImportData | null;
  selectedCategories: Set<ImportCategory>;
  allSelected: boolean;
  isImporting: boolean;
  onToggleCategory: (category: ImportCategory) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onConfirm: () => void;
}

export function ImportPreviewDialog({
  open,
  onOpenChange,
  parsedData,
  selectedCategories,
  allSelected,
  isImporting,
  onToggleCategory,
  onSelectAll,
  onDeselectAll,
  onConfirm,
}: ImportPreviewDialogProps) {
  const t = useTranslations('settings.importPreview');
  const [expandedCategory, setExpandedCategory] = useState<ImportCategory | null>(null);

  if (!parsedData) return null;

  const categoryLabels: Record<ImportCategory, string> = {
    systemInstructions: t('systemInstructions'),
    generalSettings: t('generalSettings'),
    searchServices: t('searchServices'),
    mcpServices: t('mcpServices'),
    providers: t('providers'),
    defaultModel: t('defaultModel'),
    customModelInfo: t('customModelInfo'),
  };

  const getCategoryDetail = (category: ImportCategory): string | null => {
    const config = parsedData.config;
    switch (category) {
      case 'searchServices':
        return config.searchServiceConfigs ? t('itemCount', { count: config.searchServiceConfigs.length }) : null;
      case 'mcpServices':
        return config.mcpConfigs ? t('itemCount', { count: config.mcpConfigs.length }) : null;
      case 'providers':
        return config.providers ? t('itemCount', { count: config.providers.length }) : null;
      case 'customModelInfo':
        return config.customModelInfo ? t('itemCount', { count: Object.keys(config.customModelInfo).length }) : null;
      default:
        return null;
    }
  };

  const getCategoryPreview = (category: ImportCategory): string | null => {
    const config = parsedData.config;
    switch (category) {
      case 'systemInstructions':
        return config.systemInstructions
          ? config.systemInstructions.length > 100
            ? config.systemInstructions.slice(0, 100) + '...'
            : config.systemInstructions
          : null;
      case 'searchServices':
        return config.searchServiceConfigs ? config.searchServiceConfigs.map((s) => s.search_service).join(', ') : null;
      case 'mcpServices':
        return config.mcpConfigs ? config.mcpConfigs.map((m) => m.name).join(', ') : null;
      case 'providers':
        return config.providers ? config.providers.map((p) => p.name).join(', ') : null;
      default:
        return null;
    }
  };

  const showVersionWarning = parsedData.version && parsedData.version !== '4.0.0';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            {parsedData.version && (
              <span>
                {t('version')}: {parsedData.version}
              </span>
            )}
            {parsedData.timestamp && (
              <span>
                {t('exportTime')}: {new Date(parsedData.timestamp).toLocaleString()}
              </span>
            )}
          </div>

          {showVersionWarning && (
            <div className="flex items-center gap-2 p-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 text-xs">
              <IconAlertCircle className="w-3.5 h-3.5" />
              <span>{t('versionMismatch', { version: parsedData.version ?? '' })}</span>
            </div>
          )}

          <div className="flex justify-end">
            <button
              onClick={allSelected ? onDeselectAll : onSelectAll}
              className="text-xs text-primary hover:text-primary/80 transition-colors"
            >
              {allSelected ? t('deselectAll') : t('selectAll')}
            </button>
          </div>

          <div className="border rounded-lg divide-y max-h-[360px] overflow-y-auto">
            {Array.from(parsedData.availableCategories).map((category) => {
              const detail = getCategoryDetail(category);
              const preview = getCategoryPreview(category);
              const isExpanded = expandedCategory === category;

              return (
                <div key={category} className="flex flex-col">
                  <div
                    className="flex items-center gap-3 p-3 hover:bg-muted/50 cursor-pointer transition-colors"
                    onClick={() => onToggleCategory(category)}
                  >
                    <div
                      className={`w-4 h-4 border-2 rounded flex items-center justify-center transition-colors flex-shrink-0 ${
                        selectedCategories.has(category) ? 'bg-primary border-primary' : 'border-muted-foreground/30'
                      }`}
                    >
                      {selectedCategories.has(category) && (
                        <IconCheckCircle className="w-2.5 h-2.5 text-primary-foreground" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{categoryLabels[category]}</span>
                        {detail && <span className="text-xs text-muted-foreground">{detail}</span>}
                      </div>
                    </div>
                    {preview && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setExpandedCategory(isExpanded ? null : category);
                        }}
                        className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
                      >
                        {isExpanded ? (
                          <IconChevronUp className="w-3.5 h-3.5" />
                        ) : (
                          <IconChevronDown className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                  </div>
                  {isExpanded && preview && (
                    <div className="px-10 pb-3 text-xs text-muted-foreground break-all">{preview}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isImporting}>
            {t('cancel')}
          </Button>
          <Button onClick={onConfirm} disabled={isImporting || selectedCategories.size === 0}>
            {isImporting ? (
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                <span>{t('confirm')}</span>
              </div>
            ) : (
              t('confirm')
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
