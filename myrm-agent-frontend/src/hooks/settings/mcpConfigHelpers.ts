import type { MCPServiceConfig } from '@/store/useConfigStore';
import type { MCPOptionsResponse } from '@/services/llm-config';
import type { MCPScanFinding, MCPScanResult } from '@/store/config/types';

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

export interface PendingReloadConfirmation {
  configs: MCPServiceConfig[];
  onComplete?: () => void;
  toast?: { title: string; description?: string };
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
  togglingIndex: number | null;
  validationSuccess: boolean;
  validationError: string;
  validationLatency: number | null;
  scanFindings: MCPScanFinding[];
  isLiveScanning: boolean;
  errors: Record<string, string>;
  setErrors: (errors: Record<string, string>) => void;

  pendingDescriptionChoice: PendingDescriptionChoice | null;
  pendingRiskAck: PendingRiskAcknowledgement | null;
  pendingToggleAck: PendingToggleAcknowledgement | null;
  pendingReloadConfirm: PendingReloadConfirmation | null;

  mcpStatus: Record<string, { available: boolean; pending?: boolean; latency?: number }>;
  mcpOptions: MCPOptionsResponse | null;

  validateForm: () => boolean;
  resetForm: () => void;
  handleAddConfig: () => void;
  handleEditConfig: (index: number) => void;
  handleSaveConfig: () => Promise<void>;
  handleConfirmDescription: (chosenDescription: string) => void;
  handleCancelDescriptionChoice: () => void;
  handleConfirmRiskAck: () => Promise<void>;
  handleCancelRiskAck: () => void;
  handleConfirmToggleAck: () => Promise<void>;
  handleCancelToggleAck: () => void;
  handleConfirmReload: () => void;
  handleCancelReload: () => void;
  persistConfigs: (configs: MCPServiceConfig[], meta?: Omit<PendingReloadConfirmation, 'configs'>) => void;
  handleToggleConfig: (index: number) => void;
  handleDeleteConfig: (index: number) => void;
  handleDeleteCancel: () => void;

  connectionTypeOptions: Array<{ value: string; label: string; description: string }>;
  supportsStdio: boolean;
  importPlaceholder: string;
}

export function buildConnectionTypeOptions(
  mcpOptions: MCPOptionsResponse | null,
): Array<{ value: string; label: string; description: string }> {
  const allOptions = [
    { value: 'sse', label: 'SSE', description: 'Server-Sent Events' },
    { value: 'stdio', label: 'STDIO', description: 'Standard I/O' },
    { value: 'streamable_http', label: 'Streamable HTTP', description: 'HTTP Streaming' },
  ];
  if (!mcpOptions) {
    return allOptions;
  }
  return allOptions.filter((option) => mcpOptions.allowedTypes.includes(option.value));
}

export function buildImportPlaceholder(
  supportsStdio: boolean,
  t: (key: string) => string,
): string {
  const headerHint = supportsStdio ? t('mcpImportDescription') : t('mcpImportDescriptionSandbox');
  if (supportsStdio) {
    return `${headerHint}

{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
      "env": { "API_KEY": "..." }
    },
    "remote-server": {
      "type": "sse",
      "url": "https://mcp.example.com/sse",
      "headers": { "Authorization": "Bearer ..." }
    }
  }
}`;
  }
  return `${headerHint}

{
  "mcpServers": {
    "sse-server": {
      "type": "sse",
      "url": "https://mcp.example.com/sse",
      "headers": { "Authorization": "Bearer ..." }
    },
    "http-server": {
      "type": "streamable_http",
      "url": "https://mcp.example.com/mcp"
    }
  }
}`;
}

export function parseFinalFormData(
  formData: MCPServiceConfig,
  rawArgsInput: string,
  t: (key: string) => string,
): { data: MCPServiceConfig | null; error?: string } {
  let processedArgs: string[] = [];
  if (formData.type === 'stdio' && rawArgsInput.trim()) {
    try {
      const trimmedInput = rawArgsInput.trim();
      if (trimmedInput.startsWith('[') && trimmedInput.endsWith(']')) {
        const parsedArgs = JSON.parse(trimmedInput);
        if (Array.isArray(parsedArgs)) {
          processedArgs = parsedArgs.map((arg) => String(arg)).filter((arg) => arg.trim() !== '');
        } else {
          return { data: null, error: t('mcpArgsErrorNotArray') };
        }
      } else {
        processedArgs = rawArgsInput.split('\n').filter((arg) => arg.trim() !== '');
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : '';
      return {
        data: null,
        error: detail ? `${t('mcpArgsErrorParse')}: ${detail}` : t('mcpArgsErrorParse'),
      };
    }
  } else if (formData.type !== 'stdio') {
    processedArgs = rawArgsInput.split('\n').filter((arg) => arg.trim() !== '');
  }

  return {
    data: {
      ...formData,
      args: processedArgs,
      keepaliveInterval:
        formData.type === 'sse' || formData.type === 'streamable_http'
          ? (formData.keepaliveInterval ?? null)
          : null,
    },
  };
}

export function validateMCPFormFields(
  formData: MCPServiceConfig,
  t: (key: string) => string,
): Record<string, string> {
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

  if (formData.type === 'stdio' && !formData.command?.trim()) {
    newErrors.command = t('mcpCommandRequired');
  }

  const keepaliveInterval = formData.keepaliveInterval ?? null;
  if ((formData.type === 'sse' || formData.type === 'streamable_http') && keepaliveInterval !== null) {
    if (!Number.isFinite(keepaliveInterval) || keepaliveInterval < 5) {
      newErrors.keepaliveInterval = t('mcpKeepaliveIntervalMin');
    }
  }

  if (!formData.description.trim()) {
    newErrors.description = t('mcpDescriptionRequired');
  }

  return newErrors;
}

export type MCPServiceStatusEntry = { available: boolean; pending?: boolean; latency?: number };

export function buildInitialMcpStatusMap(
  configs: MCPServiceConfig[],
): Record<string, MCPServiceStatusEntry> {
  const initialStatus: Record<string, MCPServiceStatusEntry> = {};
  for (const config of configs) {
    initialStatus[config.name] = config.enabled
      ? { available: false, pending: true }
      : { available: false };
  }
  return initialStatus;
}

export async function runParallelMcpStatusValidation(
  configs: MCPServiceConfig[],
  validateMCPConfig: (config: MCPServiceConfig) => Promise<{ success: boolean; latency?: number }>,
  onUpdate: (name: string, status: MCPServiceStatusEntry) => void,
  isCancelled: () => boolean,
): Promise<void> {
  const configHasSecretRefs = (cfg: MCPServiceConfig): boolean =>
    Object.values(cfg.headers || {}).some((v) => v.includes('{{secret:'));

  const validateOne = async (config: MCPServiceConfig) => {
    if (isCancelled() || !config.enabled) {
      return;
    }
    if (configHasSecretRefs(config)) {
      if (!isCancelled()) {
        onUpdate(config.name, { available: true });
      }
      return;
    }
    try {
      const result = await validateMCPConfig(config);
      if (!isCancelled()) {
        onUpdate(config.name, {
          available: !!result.success,
          latency: result.success ? result.latency : undefined,
        });
      }
    } catch {
      if (!isCancelled()) {
        onUpdate(config.name, { available: false });
      }
    }
  };

  await Promise.allSettled(configs.map((cfg) => validateOne(cfg)));
}

export function scheduleDebouncedLiveScan(
  draft: MCPServiceConfig | null,
  requestRef: { current: number },
  scanFn: (cfg: MCPServiceConfig) => Promise<{ findings?: MCPScanFinding[] }>,
  setScanFindings: (findings: MCPScanFinding[]) => void,
  setIsLiveScanning: (scanning: boolean) => void,
): (() => void) | undefined {
  if (!draft?.name.trim()) {
    setScanFindings([]);
    return undefined;
  }
  const requestId = requestRef.current + 1;
  requestRef.current = requestId;
  const timer = window.setTimeout(async () => {
    setIsLiveScanning(true);
    try {
      const scanResult = await scanFn(draft);
      if (requestRef.current === requestId) {
        setScanFindings(scanResult.findings ?? []);
      }
    } catch {
      if (requestRef.current === requestId) {
        setScanFindings([]);
      }
    } finally {
      if (requestRef.current === requestId) {
        setIsLiveScanning(false);
      }
    }
  }, 500);
  return () => window.clearTimeout(timer);
}


