import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import useConfigStore, { MCPServiceConfig } from '@/store/useConfigStore';
import { getMCPOptions, MCPOptionsResponse, scanMCPConfig } from '@/services/llm-config';
import type { MCPScanFinding, MCPScanResult } from '@/store/config/types';
import { buildLastScanSummary, gateMcpEnable, mcpConfigHasSecretRefs } from '@/hooks/useMcpSecurityGate';
import { formatMcpGateBlockedMessage } from '@/lib/utils/mcpScanFindingText';
import { useToast } from '@/hooks/useToast';
import { useTranslations } from 'next-intl';

// 默认表单数据
export const DEFAULT_FORM_DATA: MCPServiceConfig = {
  name: '',
  type: 'sse',
  url: '',
  command: '',
  args: [],
  description: '',
  enabled: true,
  headers: null,
  extra_params: {},
  hostSerial: false,
  keepaliveInterval: null,
};

/** 描述选择弹窗的待确认数据 */
export interface PendingDescriptionChoice {
  finalFormData: MCPServiceConfig;
  serverInstructions: string;
}

export interface PendingRiskAcknowledgement {
  finalFormData: MCPServiceConfig;
  scanResult: MCPScanResult;
}

export interface PendingToggleAcknowledgement {
  index: number;
  scanResult: MCPScanResult;
}

export interface UseMCPConfigReturn {
  configs: MCPServiceConfig[];
  setConfigs: (configs: MCPServiceConfig[]) => void;

  formData: MCPServiceConfig;
  setFormData: (data: MCPServiceConfig) => void;
  rawArgsInput: string;
  setRawArgsInput: (value: string) => void;
  editingIndex: number | null;
  setEditingIndex: (index: number | null) => void;

  showConfigModal: boolean;
  setShowConfigModal: (show: boolean) => void;
  showImportModal: boolean;
  setShowImportModal: (show: boolean) => void;
  deleteConfirmIndex: number | null;
  setDeleteConfirmIndex: (index: number | null) => void;

  isValidating: boolean;
  /** Index of MCP row running enable security gate (scan + verify). */
  togglingIndex: number | null;
  validationSuccess: boolean;
  validationError: string;
  validationLatency: number | null;
  scanFindings: MCPScanFinding[];
  isLiveScanning: boolean;
  errors: Record<string, string>;
  setErrors: (errors: Record<string, string>) => void;

  /** 待选择描述的数据（验证通过后、需要用户选择描述时） */
  pendingDescriptionChoice: PendingDescriptionChoice | null;
  pendingRiskAck: PendingRiskAcknowledgement | null;
  pendingToggleAck: PendingToggleAcknowledgement | null;

  mcpStatus: Record<string, { available: boolean; pending?: boolean; latency?: number }>;
  mcpOptions: MCPOptionsResponse | null;

  validateForm: () => boolean;
  resetForm: () => void;
  handleAddConfig: () => void;
  handleEditConfig: (index: number) => void;
  handleSaveConfig: () => Promise<void>;
  /** 用户选择描述后确认保存 */
  handleConfirmDescription: (chosenDescription: string) => void;
  /** 用户取消描述选择 */
  handleCancelDescriptionChoice: () => void;
  handleConfirmRiskAck: () => Promise<void>;
  handleCancelRiskAck: () => void;
  handleConfirmToggleAck: () => Promise<void>;
  handleCancelToggleAck: () => void;
  handleToggleConfig: (index: number) => void;
  handleDeleteConfig: (index: number) => void;
  handleDeleteCancel: () => void;

  connectionTypeOptions: Array<{ value: string; label: string; description: string }>;
  supportsStdio: boolean;
  importPlaceholder: string;
}

/**
 * MCP 配置管理 Hook
 *
 * 核心流程：
 * 1. 保存 → 后端验证连接 → 若 MCP 有 instructions 且与用户描述不同 → 弹出描述选择
 * 2. 启用 → 检查 description 非空（空则阻止）
 * 3. JSON 导入 → 无 description 的配置自动禁用
 */
export function useMCPConfig(
  currentConfigs: MCPServiceConfig[],
  onSave: (configs: MCPServiceConfig[]) => void,
): UseMCPConfigReturn {
  const t = useTranslations('settings');
  const { validateMCPConfig } = useConfigStore();
  const { toast } = useToast();

  // 配置列表状态
  const [configs, setConfigs] = useState<MCPServiceConfig[]>(currentConfigs || []);

  // 表单状态
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [formData, setFormData] = useState<MCPServiceConfig>(DEFAULT_FORM_DATA);
  const [rawArgsInput, setRawArgsInput] = useState<string>('');

  // 弹窗状态
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [deleteConfirmIndex, setDeleteConfirmIndex] = useState<number | null>(null);

  // 验证状态
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
  const liveScanRequestRef = useRef(0);

  // MCP服务验证状态（三态：pending → available / unavailable）
  const [mcpStatus, setMcpStatus] = useState<
    Record<string, { available: boolean; pending?: boolean; latency?: number }>
  >({});

  // MCP 选项状态
  const [mcpOptions, setMcpOptions] = useState<MCPOptionsResponse | null>(null);

  // 同步外部配置变化
  useEffect(() => {
    const newConfigs = currentConfigs || [];
    setConfigs(newConfigs);
  }, [currentConfigs]);

  // 获取 MCP 选项
  useEffect(() => {
    getMCPOptions().then(setMcpOptions);
  }, []);

  // 根据后端配置过滤可用的连接类型选项
  const connectionTypeOptions = useMemo(() => {
    const allOptions = [
      { value: 'sse', label: 'SSE', description: 'Server-Sent Events 连接' },
      { value: 'stdio', label: 'STDIO', description: '标准输入输出连接' },
      { value: 'streamable_http', label: 'Streamable HTTP', description: 'HTTP 流式连接' },
    ];

    if (!mcpOptions) {
      return allOptions;
    }

    return allOptions.filter((option) => mcpOptions.allowedTypes.includes(option.value));
  }, [mcpOptions]);

  // 是否支持 STDIO
  const supportsStdio = useMemo(() => {
    return !mcpOptions || mcpOptions.allowedTypes.includes('stdio');
  }, [mcpOptions]);

  // 动态生成导入 placeholder
  const importPlaceholder = useMemo(() => {
    if (supportsStdio) {
      return `支持以下格式：

━━━ 格式1: 单个配置（推荐）━━━
{
  "name": "amap-maps",
  "type": "sse",
  "url": "https://mcp.amap.com/sse?key=xxx",
  "description": "高德地图服务"
}

━━━ 格式2: 多服务配置 ━━━
{
  "my-server": { "command": "npx", "args": ["-y", "mcp"] },
  "sse-server": { "type": "sse", "url": "http://..." }
}

━━━ 格式3: mcpServers 包裹 ━━━
{
  "mcpServers": {
    "server-name": { "command": "npx", "args": [...] }
  }
}

━━━ 格式4: 数组格式 ━━━
[{ "name": "s1", "type": "sse", "url": "..." }]

━━━ 可选参数 ━━━
env: { "KEY": "value" }  // 环境变量
cwd: "/path"             // 工作目录
headers: { "Auth": "..." } // HTTP 头`;
    } else {
      return `支持以下格式（仅 SSE/HTTP 类型）：

━━━ 格式1: 单个配置（推荐）━━━
{
  "name": "amap-maps",
  "type": "sse",
  "url": "https://mcp.amap.com/sse?key=xxx",
  "description": "高德地图服务"
}

━━━ 格式2: 多服务配置 ━━━
{
  "sse-server": { "type": "sse", "url": "http://..." },
  "http-server": { "type": "streamableHttp", "url": "http://..." }
}

━━━ 格式3: mcpServers 包裹 ━━━
{
  "mcpServers": {
    "server-name": { "type": "sse", "url": "..." }
  }
}

━━━ 格式4: 数组格式 ━━━
[{ "name": "s1", "type": "sse", "url": "..." }]

━━━ 可选参数 ━━━
headers: { "Authorization": "Bearer ..." } // HTTP 头

⚠️ 注：Sandbox 环境不支持 STDIO 类型`;
    }
  }, [supportsStdio]);

  // 页面加载时自动批量验证所有MCP配置
  useEffect(() => {
    if (!configs.length) return;
    let cancelled = false;

    const initialStatus: Record<string, { available: boolean; pending?: boolean; latency?: number }> = {};
    for (const config of configs) {
      initialStatus[config.name] = config.enabled ? { available: false, pending: true } : { available: false };
    }
    setMcpStatus(initialStatus);

    const configHasSecretRefs = (cfg: MCPServiceConfig): boolean =>
      Object.values(cfg.headers || {}).some((v) => v.includes('{{secret:'));

    const validateAll = async () => {
      for (const config of configs) {
        if (cancelled) return;
        if (!config.enabled) continue;
        if (configHasSecretRefs(config)) {
          if (!cancelled) {
            setMcpStatus((prev) => ({
              ...prev,
              [config.name]: { available: true },
            }));
          }
          continue;
        }
        try {
          const result = await validateMCPConfig(config);
          if (!cancelled) {
            setMcpStatus((prev) => ({
              ...prev,
              [config.name]: {
                available: !!result.success,
                latency: result.success ? result.latency : undefined,
              },
            }));
          }
        } catch {
          if (!cancelled) {
            setMcpStatus((prev) => ({
              ...prev,
              [config.name]: { available: false },
            }));
          }
        }
      }
    };
    validateAll();
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
  }, []);

  const buildFinalFormData = useCallback((): MCPServiceConfig | null => {
    let processedArgs: string[] = [];
    if (formData.type === 'stdio' && rawArgsInput.trim()) {
      try {
        const trimmedInput = rawArgsInput.trim();
        if (trimmedInput.startsWith('[') && trimmedInput.endsWith(']')) {
          const parsedArgs = JSON.parse(trimmedInput);
          if (Array.isArray(parsedArgs)) {
            processedArgs = parsedArgs.map((arg) => String(arg)).filter((arg) => arg.trim() !== '');
          } else {
            throw new Error('JSON格式必须是数组');
          }
        } else {
          processedArgs = rawArgsInput.split('\n').filter((arg) => arg.trim() !== '');
        }
      } catch (error) {
        setValidationError(`参数格式错误: ${error instanceof Error ? error.message : '无法解析参数'}`);
        return null;
      }
    } else if (formData.type !== 'stdio') {
      processedArgs = rawArgsInput.split('\n').filter((arg) => arg.trim() !== '');
    }
    return { ...formData, args: processedArgs };
  }, [formData, rawArgsInput]);

  useEffect(() => {
    if (!showConfigModal) return;
    const draft = buildFinalFormData();
    if (!draft?.name.trim()) {
      setScanFindings([]);
      return;
    }

    const requestId = liveScanRequestRef.current + 1;
    liveScanRequestRef.current = requestId;
    const timer = window.setTimeout(async () => {
      setIsLiveScanning(true);
      try {
        const scanResult = await scanMCPConfig(draft);
        if (liveScanRequestRef.current !== requestId) return;
        setScanFindings(scanResult.findings ?? []);
      } catch {
        if (liveScanRequestRef.current !== requestId) return;
        setScanFindings([]);
      } finally {
        if (liveScanRequestRef.current === requestId) {
          setIsLiveScanning(false);
        }
      }
    }, 500);

    return () => window.clearTimeout(timer);
  }, [showConfigModal, buildFinalFormData]);

  const validateForm = useCallback(() => {
    const newErrors: Record<string, string> = {};

    if (!formData.name.trim()) {
      newErrors.name = t('mcpNameRequired');
    }

    if (formData.type === 'sse' || formData.type === 'streamable_http') {
      if (!formData.url?.trim()) {
        newErrors.url = t('mcpUrlRequired');
      } else {
        try {
          new URL(formData.url);
        } catch {
          newErrors.url = t('mcpUrlInvalid');
        }
      }
    }

    if (formData.type === 'stdio') {
      if (!formData.command?.trim()) {
        newErrors.command = t('mcpCommandRequired');
      }
    }

    if ((formData.type === 'sse' || formData.type === 'streamable_http') && formData.keepaliveInterval !== null) {
      if (!Number.isFinite(formData.keepaliveInterval) || formData.keepaliveInterval < 5) {
        newErrors.keepaliveInterval = t('mcpKeepaliveIntervalMin');
      }
    }

    if (!formData.description.trim()) {
      newErrors.description = t('mcpDescriptionRequired');
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formData, t]);

  // 添加新配置
  const handleAddConfig = useCallback(() => {
    setFormData(DEFAULT_FORM_DATA);
    setRawArgsInput('');
    setEditingIndex(null);
    setErrors({});
    setValidationError('');
    setValidationSuccess(false);
    setShowConfigModal(true);
  }, []);

  // 编辑配置
  const handleEditConfig = useCallback(
    (index: number) => {
      // 边缘场景处理：检查索引有效性
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
      setConfigs(newConfigs);
      onSave(newConfigs);
      toast({
        title: editingIndex !== null ? t('mcpUpdateSuccess') : t('mcpAddSuccess'),
        description: t('mcpSaveSuccessDesc'),
      });
      resetForm();
    },
    [configs, editingIndex, onSave, t, toast, resetForm],
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
        setValidationError(
          formatMcpGateBlockedMessage(
            {
              verifyError: gate.verifyError,
              verifyFindings: gate.verifyFindings,
              staticFindings: gate.scanResult.findings,
              fallback: t('mcpScanBlocked'),
            },
            t,
          ),
        );
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
    [commitConfig, t, toast, validateMCPConfig],
  );

  const handleSaveConfig = useCallback(async () => {
    if (!validateForm()) return;
    const finalFormData = buildFinalFormData();
    if (!finalFormData) return;

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
    if (!pendingRiskAck) return;
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
      if (!pendingDescriptionChoice) return;
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
      setConfigs(newConfigs);
      onSave(newConfigs);
    },
    [configs, onSave],
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
            toast({
              title: t('mcpScanBlocked'),
              description: formatMcpGateBlockedMessage(
                {
                  verifyError: gate.verifyError,
                  verifyFindings: gate.verifyFindings,
                  staticFindings: gate.scanResult.findings,
                  fallback: t('mcpScanBlocked'),
                },
                t,
              ),
              variant: 'destructive',
            });
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
    [configs, applyToggleAtIndex, t, toast],
  );

  const handleConfirmToggleAck = useCallback(async () => {
    if (!pendingToggleAck) return;
    const { index } = pendingToggleAck;
    const config = configs[index];
    setPendingToggleAck(null);
    setTogglingIndex(index);
    try {
      const gate = await gateMcpEnable(config, { acknowledgedHighRisks: true });
      if (!gate.allowed) {
        toast({
          title: t('mcpScanBlocked'),
          description: formatMcpGateBlockedMessage(
            {
              verifyError: gate.verifyError,
              verifyFindings: gate.verifyFindings,
              staticFindings: gate.scanResult.findings,
              fallback: t('mcpScanBlocked'),
            },
            t,
          ),
          variant: 'destructive',
        });
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
  }, [pendingToggleAck, configs, applyToggleAtIndex, t, toast]);

  const handleCancelToggleAck = useCallback(() => {
    setPendingToggleAck(null);
  }, []);

  // 删除配置
  const handleDeleteConfig = useCallback(
    (index: number) => {
      // 边缘场景处理：检查索引有效性
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
      setConfigs(newConfigs);
      onSave(newConfigs);
      setDeleteConfirmIndex(null);

      toast({
        title: t('mcpDeleteSuccess'),
        description: t('mcpDeleteSuccessDesc'),
      });
    },
    [configs, onSave, t, toast],
  );

  // 取消删除
  const handleDeleteCancel = useCallback(() => {
    setDeleteConfirmIndex(null);
  }, []);

  return {
    configs,
    setConfigs,
    formData,
    setFormData,
    rawArgsInput,
    setRawArgsInput,
    editingIndex,
    setEditingIndex,
    showConfigModal,
    setShowConfigModal,
    showImportModal,
    setShowImportModal,
    deleteConfirmIndex,
    setDeleteConfirmIndex,
    isValidating,
    togglingIndex,
    validationSuccess,
    validationError,
    validationLatency,
    scanFindings,
    isLiveScanning,
    errors,
    setErrors,
    pendingDescriptionChoice,
    pendingRiskAck,
    pendingToggleAck,
    mcpStatus,
    mcpOptions,
    validateForm,
    resetForm,
    handleAddConfig,
    handleEditConfig,
    handleSaveConfig,
    handleConfirmDescription,
    handleCancelDescriptionChoice,
    handleConfirmRiskAck,
    handleCancelRiskAck,
    handleConfirmToggleAck,
    handleCancelToggleAck,
    handleToggleConfig,
    handleDeleteConfig,
    handleDeleteCancel,
    connectionTypeOptions,
    supportsStdio,
    importPlaceholder,
  };
}
