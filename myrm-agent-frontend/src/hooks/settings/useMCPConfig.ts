import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import useConfigStore, { MCPServiceConfig } from '@/store/useConfigStore';
import { getMCPOptions, MCPOptionsResponse, scanMCPConfig } from '@/services/llm-config';
import type { MCPScanFinding, MCPScanResult } from '@/store/config/types';
import { buildLastScanSummary, gateMcpEnable, mcpConfigHasSecretRefs } from '@/hooks/settings/useMcpSecurityGate';
import { formatMcpGateBlockedMessage } from '@/lib/utils/mcp-config';
import { useToast } from '@/hooks/shared/useToast';
import { useTranslations } from 'next-intl';
import {
  DEFAULT_FORM_DATA,
  PendingDescriptionChoice,
  PendingReloadConfirmation,
  PendingRiskAcknowledgement,
  PendingToggleAcknowledgement,
  UseMCPConfigReturn,
  buildConnectionTypeOptions,
  buildImportPlaceholder,
  buildInitialMcpStatusMap,
  parseFinalFormData,
  runParallelMcpStatusValidation,
  scheduleDebouncedLiveScan,
  validateMCPFormFields,
} from '@/hooks/settings/mcpConfigHelpers';

export { DEFAULT_FORM_DATA };
export type {
  PendingDescriptionChoice,
  PendingReloadConfirmation,
  PendingRiskAcknowledgement,
  PendingToggleAcknowledgement,
  UseMCPConfigReturn,
};

export function useMCPConfig(
  currentConfigs: MCPServiceConfig[],
  onSave: (configs: MCPServiceConfig[]) => void,
): UseMCPConfigReturn {
  const t = useTranslations('settings');
  const { validateMCPConfig } = useConfigStore();
  const { toast } = useToast();

  const [configs, setConfigs] = useState<MCPServiceConfig[]>(currentConfigs || []);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [formData, setFormData] = useState<MCPServiceConfig>(DEFAULT_FORM_DATA);
  const [rawArgsInput, setRawArgsInput] = useState<string>('');

  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [deleteConfirmIndex, setDeleteConfirmIndex] = useState<number | null>(null);

  const [isValidating, setIsValidating] = useState(false);
  const [togglingIndex, setTogglingIndex] = useState<number | null>(null);
  const [validationSuccess, setValidationSuccess] = useState(false);
  const [validationError, setValidationError] = useState('');
  const [validationLatency, setValidationLatency] = useState<number | null>(null);
  const [scanFindings, setScanFindings] = useState<MCPScanFinding[]>([]);
  const [isLiveScanning, setIsLiveScanning] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pendingDescriptionChoice, setPendingDescriptionChoice] = useState<PendingDescriptionChoice | null>(null);
  const [pendingRiskAck, setPendingRiskAck] = useState<PendingRiskAcknowledgement | null>(null);
  const [pendingToggleAck, setPendingToggleAck] = useState<PendingToggleAcknowledgement | null>(null);
  const [pendingReloadConfirm, setPendingReloadConfirm] = useState<PendingReloadConfirmation | null>(null);
  const liveScanRequestRef = useRef(0);

  const [mcpStatus, setMcpStatus] = useState<
    Record<string, { available: boolean; pending?: boolean; latency?: number }>
  >({});
  const [mcpOptions, setMcpOptions] = useState<MCPOptionsResponse | null>(null);

  useEffect(() => {
    setConfigs(currentConfigs || []);
  }, [currentConfigs]);

  useEffect(() => {
    getMCPOptions().then(setMcpOptions);
  }, []);

  const connectionTypeOptions = useMemo(() => buildConnectionTypeOptions(mcpOptions), [mcpOptions]);

  const supportsStdio = useMemo(() => {
    return !mcpOptions || mcpOptions.allowedTypes.includes('stdio');
  }, [mcpOptions]);

  const importPlaceholder = useMemo(() => buildImportPlaceholder(supportsStdio, t), [supportsStdio, t]);

  // Validate enabled MCP services in parallel so one slow server never blocks others
  useEffect(() => {
    if (!configs.length) {
      return;
    }
    let cancelled = false;
    setMcpStatus(buildInitialMcpStatusMap(configs));
    void runParallelMcpStatusValidation(
      configs,
      validateMCPConfig,
      (name, status) => setMcpStatus((prev) => ({ ...prev, [name]: status })),
      () => cancelled,
    );
    return () => {
      cancelled = true;
    };
  }, [configs, validateMCPConfig]);

  const resetForm = useCallback(() => {
    setFormData(DEFAULT_FORM_DATA);
    setRawArgsInput('');
    setEditingIndex(null);
    setShowConfigModal(false);
    setErrors({});
    setValidationError('');
    setValidationSuccess(false);
    setValidationLatency(null);
    setScanFindings([]);
    setPendingDescriptionChoice(null);
    setPendingRiskAck(null);
    setPendingToggleAck(null);
    setPendingReloadConfirm(null);
  }, []);

  const configsEqual = useCallback((a: MCPServiceConfig[], b: MCPServiceConfig[]) => {
    return JSON.stringify(a) === JSON.stringify(b);
  }, []);

  const finalizePersist = useCallback(
    (newConfigs: MCPServiceConfig[], meta?: Omit<PendingReloadConfirmation, 'configs'>) => {
      setConfigs(newConfigs);
      onSave(newConfigs);
      if (meta?.toast) {
        toast(meta.toast);
      }
      meta?.onComplete?.();
    },
    [onSave, toast],
  );

  const persistConfigs = useCallback(
    (newConfigs: MCPServiceConfig[], meta?: Omit<PendingReloadConfirmation, 'configs'>) => {
      const baseline = currentConfigs || [];
      if (configsEqual(newConfigs, baseline)) {
        finalizePersist(newConfigs, meta);
        return;
      }
      setPendingReloadConfirm({ configs: newConfigs, ...meta });
    },
    [configsEqual, currentConfigs, finalizePersist],
  );

  const handleConfirmReload = useCallback(() => {
    if (!pendingReloadConfirm) {
      return;
    }
    const { configs: newConfigs, onComplete, toast: toastMeta } = pendingReloadConfirm;
    setPendingReloadConfirm(null);
    finalizePersist(newConfigs, { onComplete, toast: toastMeta });
  }, [pendingReloadConfirm, finalizePersist]);

  const handleCancelReload = useCallback(() => {
    setPendingReloadConfirm(null);
  }, []);

  const buildFinalFormData = useCallback((): MCPServiceConfig | null => {
    const parsed = parseFinalFormData(formData, rawArgsInput, t);
    if (parsed.error) {
      setValidationError(parsed.error);
      return null;
    }
    return parsed.data;
  }, [formData, rawArgsInput, t]);

  useEffect(() => {
    if (!showConfigModal) {
      return;
    }
    return scheduleDebouncedLiveScan(
      buildFinalFormData(),
      liveScanRequestRef,
      scanMCPConfig,
      setScanFindings,
      setIsLiveScanning,
    );
  }, [showConfigModal, buildFinalFormData]);

  const formatGateError = useCallback(
    (gate: { verifyError?: string; verifyFindings?: MCPScanFinding[]; scanResult: MCPScanResult }) =>
      formatMcpGateBlockedMessage(
        {
          verifyError: gate.verifyError,
          verifyFindings: gate.verifyFindings,
          staticFindings: gate.scanResult.findings,
          fallback: t('mcpScanBlocked'),
        },
        t,
      ),
    [t],
  );

  const validateForm = useCallback(() => {
    const newErrors = validateMCPFormFields(formData, t);
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formData, t]);

  const handleAddConfig = useCallback(() => {
    setFormData(DEFAULT_FORM_DATA);
    setRawArgsInput('');
    setEditingIndex(null);
    setErrors({});
    setValidationError('');
    setValidationSuccess(false);
    setShowConfigModal(true);
  }, []);

  const handleEditConfig = useCallback(
    (index: number) => {
      if (index < 0 || index >= configs.length) {
        console.error(`Invalid config index: ${index}`);
        toast({
          title: t('mcpEditFailed'),
          description: t('mcpConfigNotFound'),
          variant: 'destructive',
        });
        return;
      }

      const config = configs[index];
      setFormData({
        ...config,
        extra_params: config.extra_params || {},
      });
      setRawArgsInput((config.args || []).join('\n'));
      setEditingIndex(index);
      setErrors({});
      setValidationError('');
      setValidationSuccess(false);
      setShowConfigModal(true);
    },
    [configs, t, toast],
  );

  const commitConfig = useCallback(
    (finalFormData: MCPServiceConfig, scanResult?: MCPScanResult) => {
      const withSummary: MCPServiceConfig = {
        ...finalFormData,
        lastScanSummary: scanResult ? buildLastScanSummary(scanResult) : finalFormData.lastScanSummary,
      };
      const newConfigs = [...configs];
      if (editingIndex !== null) {
        newConfigs[editingIndex] = withSummary;
      } else {
        newConfigs.push(withSummary);
      }
      persistConfigs(newConfigs, {
        onComplete: resetForm,
        toast: {
          title: editingIndex !== null ? t('mcpUpdateSuccess') : t('mcpAddSuccess'),
          description: t('mcpSaveSuccessDesc'),
        },
      });
    },
    [configs, editingIndex, persistConfigs, t, resetForm],
  );

  const finalizeSave = useCallback(
    async (finalFormData: MCPServiceConfig, acknowledgedHighRisks = false) => {
      const hasSecretRefs = mcpConfigHasSecretRefs(finalFormData);

      const gate = await gateMcpEnable(finalFormData, { acknowledgedHighRisks });
      setScanFindings(gate.scanResult.findings ?? []);

      if (gate.needsAcknowledgement) {
        setPendingRiskAck({ finalFormData, scanResult: gate.scanResult });
        return;
      }
      if (!gate.allowed) {
        setValidationError(formatGateError(gate));
        setValidationSuccess(false);
        return;
      }

      if (hasSecretRefs) {
        toast({ title: t('mcpSecretRefSaveHint'), description: t('mcpSecretRefSaveHintDesc') });
        commitConfig(finalFormData, gate.scanResult);
        return;
      }

      setValidationSuccess(true);
      setValidationLatency(gate.verifyLatency || null);

      if (gate.instructions && finalFormData.description.trim() !== gate.instructions.trim()) {
        setPendingDescriptionChoice({
          finalFormData: { ...finalFormData, lastScanSummary: buildLastScanSummary(gate.scanResult) },
          serverInstructions: gate.instructions,
        });
        return;
      }

      commitConfig(finalFormData, gate.scanResult);
    },
    [commitConfig, formatGateError, t, toast],
  );

  const handleSaveConfig = useCallback(async () => {
    if (!validateForm()) {
      return;
    }
    const finalFormData = buildFinalFormData();
    if (!finalFormData) {
      return;
    }

    setIsValidating(true);
    setValidationError('');
    setValidationLatency(null);

    try {
      await finalizeSave(finalFormData);
    } catch (error) {
      setValidationError(t('mcpValidationError') + (error instanceof Error ? `: ${error.message}` : ''));
      setValidationSuccess(false);
    } finally {
      setIsValidating(false);
    }
  }, [validateForm, buildFinalFormData, finalizeSave, t]);

  const handleConfirmRiskAck = useCallback(async () => {
    if (!pendingRiskAck) {
      return;
    }
    const { finalFormData } = pendingRiskAck;
    setPendingRiskAck(null);
    setIsValidating(true);
    try {
      await finalizeSave(finalFormData, true);
    } catch (error) {
      setValidationError(t('mcpValidationError') + (error instanceof Error ? `: ${error.message}` : ''));
      setValidationSuccess(false);
    } finally {
      setIsValidating(false);
    }
  }, [pendingRiskAck, finalizeSave, t]);

  const handleCancelRiskAck = useCallback(() => {
    setPendingRiskAck(null);
  }, []);

  const handleConfirmDescription = useCallback(
    (chosenDescription: string) => {
      if (!pendingDescriptionChoice) {
        return;
      }
      const finalData = {
        ...pendingDescriptionChoice.finalFormData,
        description: chosenDescription,
      };
      setPendingDescriptionChoice(null);
      commitConfig(finalData, undefined);
    },
    [pendingDescriptionChoice, commitConfig],
  );

  const handleCancelDescriptionChoice = useCallback(() => {
    setPendingDescriptionChoice(null);
  }, []);

  const applyToggleAtIndex = useCallback(
    (index: number, scanResult?: MCPScanResult) => {
      const newConfigs = [...configs];
      newConfigs[index] = {
        ...newConfigs[index],
        enabled: !newConfigs[index].enabled,
        lastScanSummary: scanResult ? buildLastScanSummary(scanResult) : newConfigs[index].lastScanSummary,
      };
      persistConfigs(newConfigs);
    },
    [configs, persistConfigs],
  );

  const handleToggleConfig = useCallback(
    async (index: number) => {
      const config = configs[index];
      if (!config.enabled && !config.description.trim()) {
        toast({
          title: t('mcpEnableBlockedTitle'),
          description: t('mcpEnableBlockedNoDesc'),
          variant: 'destructive',
        });
        return;
      }
      if (!config.enabled) {
        setTogglingIndex(index);
        try {
          const gate = await gateMcpEnable(config);
          if (gate.needsAcknowledgement) {
            setPendingToggleAck({ index, scanResult: gate.scanResult });
            return;
          }
          if (!gate.allowed) {
            toast({ title: t('mcpScanBlocked'), description: formatGateError(gate), variant: 'destructive' });
            return;
          }
          applyToggleAtIndex(index, gate.scanResult);
          return;
        } catch (error) {
          toast({
            title: t('mcpScanBlocked'),
            description: error instanceof Error ? error.message : undefined,
            variant: 'destructive',
          });
          return;
        } finally {
          setTogglingIndex(null);
        }
      }
      applyToggleAtIndex(index);
    },
    [configs, applyToggleAtIndex, formatGateError, t, toast],
  );

  const handleConfirmToggleAck = useCallback(async () => {
    if (!pendingToggleAck) {
      return;
    }
    const { index } = pendingToggleAck;
    const config = configs[index];
    setPendingToggleAck(null);
    setTogglingIndex(index);
    try {
      const gate = await gateMcpEnable(config, { acknowledgedHighRisks: true });
      if (!gate.allowed) {
        toast({ title: t('mcpScanBlocked'), description: formatGateError(gate), variant: 'destructive' });
        return;
      }
      applyToggleAtIndex(index, gate.scanResult);
    } catch (error) {
      toast({
        title: t('mcpScanBlocked'),
        description: error instanceof Error ? error.message : undefined,
        variant: 'destructive',
      });
    } finally {
      setTogglingIndex(null);
    }
  }, [pendingToggleAck, configs, applyToggleAtIndex, formatGateError, t, toast]);

  const handleCancelToggleAck = useCallback(() => {
    setPendingToggleAck(null);
  }, []);

  const handleDeleteConfig = useCallback(
    (index: number) => {
      if (index < 0 || index >= configs.length) {
        console.error(`Invalid config index for deletion: ${index}`);
        toast({
          title: t('mcpDeleteFailed'),
          description: t('mcpConfigNotFound'),
          variant: 'destructive',
        });
        setDeleteConfirmIndex(null);
        return;
      }

      const newConfigs = configs.filter((_, i) => i !== index);
      setDeleteConfirmIndex(null);
      persistConfigs(newConfigs, {
        toast: {
          title: t('mcpDeleteSuccess'),
          description: t('mcpDeleteSuccessDesc'),
        },
      });
    },
    [configs, persistConfigs, t, toast],
  );

  const handleDeleteCancel = useCallback(() => {
    setDeleteConfirmIndex(null);
  }, []);

  return {
    configs, setConfigs, formData, setFormData, rawArgsInput, setRawArgsInput,
    editingIndex, setEditingIndex, showConfigModal, setShowConfigModal,
    showImportModal, setShowImportModal, deleteConfirmIndex, setDeleteConfirmIndex,
    isValidating, togglingIndex, validationSuccess, validationError, validationLatency,
    scanFindings, isLiveScanning, errors, setErrors,
    pendingDescriptionChoice, pendingRiskAck, pendingToggleAck, pendingReloadConfirm,
    mcpStatus, mcpOptions, validateForm, resetForm,
    handleAddConfig, handleEditConfig, handleSaveConfig,
    handleConfirmDescription, handleCancelDescriptionChoice,
    handleConfirmRiskAck, handleCancelRiskAck,
    handleConfirmToggleAck, handleCancelToggleAck,
    handleConfirmReload, handleCancelReload,
    persistConfigs, handleToggleConfig, handleDeleteConfig, handleDeleteCancel,
    connectionTypeOptions, supportsStdio, importPlaceholder,
  };
}
