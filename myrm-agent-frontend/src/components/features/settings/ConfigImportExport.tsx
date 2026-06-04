'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import {
  IconDownload,
  IconUpload,
  IconAlertCircle,
  IconCheckCircle,
  IconCopy,
  IconFileText,
  IconShieldAlert,
} from '@/components/features/icons/PremiumIcons';
import { useTranslations } from 'next-intl';
import useConfigStore from '@/store/useConfigStore';
import useProviderStore from '@/store/useProviderStore';
import {
  exportConfig as exportConfigUtil,
  importConfig as importConfigUtil,
  FullExportConfig,
} from '@/store/config/importExport';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { readFromClipboard } from '@/lib/utils/clipboardUtils';
import {
  ImportPreviewDialog,
  parseImportJson,
  type ImportCategory,
  type ParsedImportData,
} from './ImportPreviewDialog';

const TOAST_AUTO_DISMISS_MS = 3000;

const ConfigImportExport: React.FC = () => {
  const t = useTranslations('settings');
  const tp = useTranslations('settings.importPreview');
  const configStore = useConfigStore();
  const providerStore = useProviderStore();
  const [importResult, setImportResult] = useState<{ success: boolean; message: string } | null>(null);
  const [copySuccess, setCopySuccess] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [exportWarningOpen, setExportWarningOpen] = useState(false);
  const [pendingExportAction, setPendingExportAction] = useState<'file' | 'clipboard' | null>(null);
  const [parsedData, setParsedData] = useState<ParsedImportData | null>(null);
  const [selectedCategories, setSelectedCategories] = useState<Set<ImportCategory>>(new Set());
  const [isImporting, setIsImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (importResult) {
      const timer = setTimeout(() => setImportResult(null), TOAST_AUTO_DISMISS_MS);
      return () => clearTimeout(timer);
    }
  }, [importResult]);

  const getFullConfigData = useCallback(() => {
    return exportConfigUtil(
      {
        systemInstructions: configStore.systemInstructions,
        fetchRawWebpage: configStore.fetchRawWebpage,
        extractDocumentText: configStore.extractDocumentText,
        generateSearchSuggestions: configStore.generateSearchSuggestions,
        enableCostEstimation: configStore.enableCostEstimation,
        searchServiceConfigs: configStore.searchServiceConfigs,
        mcpConfigs: configStore.mcpConfigs,
      },
      {
        providers: providerStore.providers,
        defaultModelConfig: providerStore.defaultModelConfig,
        customModelInfo: providerStore.customModelInfo,
      },
    );
  }, [configStore, providerStore]);

  const openPreview = useCallback(
    (json: string) => {
      const result = parseImportJson(json);
      if ('error' in result) {
        setImportResult({ success: false, message: tp(result.error) });
        return;
      }
      setParsedData(result);
      setSelectedCategories(new Set(result.availableCategories));
      setPreviewOpen(true);
      setImportResult(null);
    },
    [tp],
  );

  const handleConfirmImport = useCallback(async () => {
    if (!parsedData) return;
    setIsImporting(true);

    const filteredConfig: Partial<FullExportConfig> = {};

    if (selectedCategories.has('systemInstructions')) {
      filteredConfig.systemInstructions = parsedData.config.systemInstructions;
    }
    if (selectedCategories.has('generalSettings')) {
      filteredConfig.fetchRawWebpage = parsedData.config.fetchRawWebpage;
      filteredConfig.extractDocumentText = parsedData.config.extractDocumentText;
      filteredConfig.generateSearchSuggestions = parsedData.config.generateSearchSuggestions;
      filteredConfig.enableCostEstimation = parsedData.config.enableCostEstimation;
    }
    if (selectedCategories.has('searchServices')) {
      filteredConfig.searchServiceConfigs = parsedData.config.searchServiceConfigs;
    }
    if (selectedCategories.has('mcpServices')) {
      filteredConfig.mcpConfigs = parsedData.config.mcpConfigs;
    }
    if (selectedCategories.has('providers')) {
      filteredConfig.providers = parsedData.config.providers;
    }
    if (selectedCategories.has('defaultModel')) {
      filteredConfig.defaultModelConfig = parsedData.config.defaultModelConfig;
    }
    if (selectedCategories.has('customModelInfo')) {
      filteredConfig.customModelInfo = parsedData.config.customModelInfo;
    }

    const wrappedJson = JSON.stringify({
      version: parsedData.version,
      timestamp: parsedData.timestamp,
      config: filteredConfig,
    });

    const result = await importConfigUtil(wrappedJson, {
      setSystemInstructions: selectedCategories.has('systemInstructions')
        ? configStore.setSystemInstructions
        : undefined,
      setFetchRawWebpage: selectedCategories.has('generalSettings') ? configStore.setFetchRawWebpage : undefined,
      setExtractDocumentText: selectedCategories.has('generalSettings')
        ? configStore.setExtractDocumentText
        : undefined,
      setGenerateSearchSuggestions: selectedCategories.has('generalSettings')
        ? configStore.setGenerateSearchSuggestions
        : undefined,
      setEnableCostEstimation: selectedCategories.has('generalSettings')
        ? configStore.setEnableCostEstimation
        : undefined,
      setSearchServiceConfigs: selectedCategories.has('searchServices')
        ? configStore.setSearchServiceConfigs
        : undefined,
      setMCPConfigs: selectedCategories.has('mcpServices') ? configStore.setMCPConfigs : undefined,
      setProviders: selectedCategories.has('providers') ? providerStore.setProviders : undefined,
      setDefaultModelConfig: selectedCategories.has('defaultModel') ? providerStore.setDefaultModelConfig : undefined,
      setCustomModelInfo: selectedCategories.has('customModelInfo')
        ? (info) => {
            Object.entries(info).forEach(([key, value]) => {
              const [providerId, model] = key.split('/');
              if (providerId && model) {
                providerStore.setModelInfo(providerId, model, value);
              }
            });
          }
        : undefined,
    });

    setImportResult({ success: result.success, message: tp(result.messageKey) });
    setPreviewOpen(false);
    setIsImporting(false);
  }, [parsedData, selectedCategories, configStore, providerStore, tp]);

  const executeExport = useCallback(
    (action: 'file' | 'clipboard') => {
      const configData = getFullConfigData();
      if (action === 'file') {
        const blob = new Blob([configData], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `perplexica-config-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      } else {
        navigator.clipboard
          .writeText(configData)
          .then(() => {
            setCopySuccess(true);
            setImportResult({ success: true, message: t('configCopySuccess') });
            setTimeout(() => setCopySuccess(false), 2000);
          })
          .catch((error) => {
            console.error('Copy config failed:', error);
            setImportResult({ success: false, message: t('configCopyFailed') });
          });
      }
    },
    [getFullConfigData, t],
  );

  const handleExportWithWarning = useCallback((action: 'file' | 'clipboard') => {
    setPendingExportAction(action);
    setExportWarningOpen(true);
  }, []);

  const handleConfirmExport = useCallback(() => {
    if (pendingExportAction) {
      executeExport(pendingExportAction);
    }
    setExportWarningOpen(false);
    setPendingExportAction(null);
  }, [pendingExportAction, executeExport]);

  const handlePasteConfig = async () => {
    try {
      const text = await readFromClipboard();
      if (!text.trim()) {
        setImportResult({ success: false, message: t('clipboardEmpty') });
        return;
      }
      openPreview(text);
    } catch (error) {
      console.error('Paste config failed:', error);
      setImportResult({
        success: false,
        message: error instanceof Error ? error.message : t('configPasteFailed'),
      });
    }
  };

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      openPreview(text);
    } catch (error) {
      setImportResult({
        success: false,
        message: error instanceof Error ? error.message : 'Failed to read file',
      });
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const toggleCategory = (category: ImportCategory) => {
    setSelectedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  const allSelected = parsedData && selectedCategories.size === parsedData.availableCategories.size;

  return (
    <div className="flex flex-col space-y-4">
      <div className="flex flex-col space-y-3">
        <p className="text-sm text-black/70 dark:text-white/70">{t('configImportExportDesc')}</p>

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => handleExportWithWarning('file')}
            className="flex items-center justify-center space-x-2 flex-1 px-4 py-2 border border-border rounded-lg bg-background hover:bg-muted transition-colors text-sm font-medium text-black/90 dark:text-white/90"
          >
            <IconDownload className="w-4 h-4" />
            <span>{t('exportConfig')}</span>
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center justify-center space-x-2 flex-1 px-4 py-2 border border-border rounded-lg bg-background hover:bg-muted transition-colors text-sm font-medium text-black/90 dark:text-white/90"
          >
            <IconUpload className="w-4 h-4" />
            <span>{t('importConfig')}</span>
          </button>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => handleExportWithWarning('clipboard')}
            disabled={copySuccess}
            className="flex items-center justify-center space-x-2 flex-1 px-4 py-2 border border-border rounded-lg bg-background hover:bg-muted transition-colors text-sm font-medium text-black/90 dark:text-white/90 disabled:opacity-50"
          >
            {copySuccess ? (
              <>
                <IconCheckCircle className="w-4 h-4 text-green-500" />
                <span>{t('copied')}</span>
              </>
            ) : (
              <>
                <IconCopy className="w-4 h-4" />
                <span>{t('copyConfig')}</span>
              </>
            )}
          </button>

          <button
            onClick={handlePasteConfig}
            className="flex items-center justify-center space-x-2 flex-1 px-4 py-2 border border-border rounded-lg bg-background hover:bg-muted transition-colors text-sm font-medium text-black/90 dark:text-white/90"
          >
            <IconUpload className="w-4 h-4" />
            <span>{t('pasteConfig')}</span>
          </button>
        </div>

        <input ref={fileInputRef} type="file" accept=".json" onChange={handleFileSelect} className="hidden" />

        {importResult && (
          <div
            className={`flex items-center space-x-2 p-3 rounded-lg transition-opacity ${
              importResult.success
                ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
            }`}
          >
            {importResult.success ? <IconCheckCircle className="w-4 h-4" /> : <IconAlertCircle className="w-4 h-4" />}
            <span className="text-sm">{importResult.message}</span>
          </div>
        )}

        <div className="flex items-start space-x-2 p-3 bg-secondary/50 dark:bg-secondary/50 rounded-lg border border-border">
          <IconFileText className="w-4 h-4 text-black/70 dark:text-white/70 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-black/70 dark:text-white/70">
            <p className="font-medium mb-1 text-black/90 dark:text-white/90">{t('configImportExportNote')}</p>
            <ul className="list-disc list-inside space-y-1 text-xs">
              <li>{t('configExportNote')}</li>
              <li>{t('configImportNote')}</li>
              <li>{t('configBackupNote')}</li>
              <li>{t('configClipboardNote')}</li>
            </ul>
          </div>
        </div>
      </div>

      <ImportPreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        parsedData={parsedData}
        selectedCategories={selectedCategories}
        allSelected={!!allSelected}
        isImporting={isImporting}
        onToggleCategory={toggleCategory}
        onSelectAll={() => {
          if (parsedData) setSelectedCategories(new Set(parsedData.availableCategories));
        }}
        onDeselectAll={() => setSelectedCategories(new Set())}
        onConfirm={handleConfirmImport}
      />

      <ExportWarningDialog
        open={exportWarningOpen}
        onOpenChange={setExportWarningOpen}
        onConfirm={handleConfirmExport}
      />
    </div>
  );
};

interface ExportWarningDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

function ExportWarningDialog({ open, onOpenChange, onConfirm }: ExportWarningDialogProps) {
  const t = useTranslations('settings.exportWarning');

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconShieldAlert className="w-[18px] h-[18px] text-amber-500" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>{t('message')}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button onClick={onConfirm}>{t('confirm')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ConfigImportExport;
