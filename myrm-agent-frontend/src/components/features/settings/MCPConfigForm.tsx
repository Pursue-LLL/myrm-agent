import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { MCPServiceConfig } from '@/store/useConfigStore';
import type { MCPScanResult } from '@/store/config/types';
import { useMCPConfig } from '@/hooks/useMCPConfig';
import { MCPConfigList } from './mcp/MCPConfigList';
import { MCPConfigEditor } from './mcp/MCPConfigEditor';
import { MCPJsonImporter } from './mcp/MCPJsonImporter';
import { DeleteConfirmDialog } from './mcp/DeleteConfirmDialog';
import { useToast } from '@/hooks/useToast';
import { parseMCPConfigsFromJSON } from '@/lib/utils/mcpConfigParser';
import { buildLastScanSummary, gateMcpConfigBatch } from '@/hooks/useMcpSecurityGate';
import { getMcpFindingDescription } from '@/lib/utils/mcpScanFindingText';
import { MCPScanAckDialog } from './mcp/MCPScanAckDialog';

interface MCPConfigFormProps {
  currentConfigs: MCPServiceConfig[];
  onSave: (configs: MCPServiceConfig[]) => void;
}

const MCPConfigForm = ({ currentConfigs, onSave }: MCPConfigFormProps) => {
  const t = useTranslations('settings');
  const { toast } = useToast();

  // JSON导入状态（单独管理，因为有复杂的导入逻辑）
  const [importJsonText, setImportJsonText] = useState('');
  const [importError, setImportError] = useState('');
  const [pendingImportAck, setPendingImportAck] = useState<{
    configsToImport: MCPServiceConfig[];
    ackServerName: string;
    ackFindings: MCPScanResult['findings'];
    newConfigs: MCPServiceConfig[];
    skippedCount: number;
    skippedUnsupportedCount: number;
  } | null>(null);

  // 使用自定义Hook管理所有状态和逻辑
  const mcpConfig = useMCPConfig(currentConfigs, onSave);

  const finishImport = useCallback(
    (
      configsToImport: MCPServiceConfig[],
      scanResults: MCPScanResult[],
      baseConfigs: MCPServiceConfig[],
      meta: { skippedCount: number; skippedUnsupportedCount: number },
    ) => {
      const newConfigs = [...baseConfigs];
      let addedCount = 0;
      let disabledCount = 0;

      for (let importIdx = 0; importIdx < configsToImport.length; importIdx += 1) {
        const importedConfig = configsToImport[importIdx];
        const scanResult = scanResults[importIdx];
        if (scanResult) {
          importedConfig.lastScanSummary = buildLastScanSummary(scanResult);
        }
        if (!importedConfig.description.trim()) {
          importedConfig.enabled = false;
          disabledCount++;
        }
        newConfigs.push(importedConfig);
        addedCount++;
      }

      mcpConfig.setConfigs(newConfigs);
      onSave(newConfigs);
      mcpConfig.setShowImportModal(false);
      setImportJsonText('');
      setPendingImportAck(null);

      const parts: string[] = [t('mcpImportSuccessDesc', { count: addedCount })];
      if (meta.skippedCount > 0) parts.push(t('mcpImportSkipped', { count: meta.skippedCount }));
      if (meta.skippedUnsupportedCount > 0) {
        parts.push(t('mcpImportUnsupportedSkipped', { count: meta.skippedUnsupportedCount }));
      }
      if (disabledCount > 0) parts.push(t('mcpImportDisabledNoDesc', { count: disabledCount }));

      toast({
        title: t('mcpImportSuccess'),
        description: parts.join(' · '),
      });
    },
    [mcpConfig, onSave, t, toast],
  );

  const handleConfirmImportAck = useCallback(async () => {
    if (!pendingImportAck) return;
    const { configsToImport, newConfigs, ...meta } = pendingImportAck;
    const batchGate = await gateMcpConfigBatch(configsToImport, true);
    if (batchGate.blocked || batchGate.needsAcknowledgement) {
      setImportError(t('mcpScanBlocked'));
      setPendingImportAck(null);
      return;
    }
    finishImport(configsToImport, batchGate.scanResults, newConfigs, meta);
  }, [pendingImportAck, finishImport, t]);

  // JSON导入处理（保留在主组件，因为逻辑复杂且依赖多个状态）
  const handleImportJson = useCallback(async () => {
    setImportError('');

    if (!importJsonText.trim()) {
      setImportError(t('mcpImportEmptyError'));
      return;
    }

    try {
      const importedConfigs = parseMCPConfigsFromJSON(importJsonText);

      if (importedConfigs.length === 0) {
        setImportError(t('mcpImportFormatError'));
        return;
      }

      // 过滤不支持的类型
      const allowedTypes = mcpConfig.mcpOptions?.allowedTypes || ['sse', 'stdio', 'streamable_http'];
      const filteredConfigs = importedConfigs.filter((config) => allowedTypes.includes(config.type));
      const skippedUnsupportedCount = importedConfigs.length - filteredConfigs.length;

      if (filteredConfigs.length === 0) {
        if (skippedUnsupportedCount > 0) {
          setImportError(t('mcpImportUnsupportedTypeError'));
        } else {
          setImportError(t('mcpImportNoServersError'));
        }
        return;
      }

      const existingNames = new Set(mcpConfig.configs.map((c) => c.name));
      const newConfigs = [...mcpConfig.configs];
      let skippedCount = 0;

      const configsToImport: typeof filteredConfigs = [];
      for (const importedConfig of filteredConfigs) {
        if (existingNames.has(importedConfig.name)) {
          skippedCount++;
          continue;
        }
        configsToImport.push(importedConfig);
      }

      if (configsToImport.length > 0) {
        const batchGate = await gateMcpConfigBatch(configsToImport);
        if (batchGate.blocked) {
          const blockedIndex = configsToImport.findIndex((cfg) => cfg.name === batchGate.blocked?.name);
          const scanResult = batchGate.scanResults[blockedIndex] ?? batchGate.scanResults[0];
          const first = scanResult?.findings[0];
          setImportError(
            first ? `${t('mcpScanBlocked')}: ${getMcpFindingDescription(first, t)}` : t('mcpScanBlocked'),
          );
          return;
        }
        if (batchGate.needsAcknowledgement) {
          setPendingImportAck({
            configsToImport,
            ackServerName: batchGate.needsAcknowledgement.config.name,
            ackFindings: batchGate.needsAcknowledgement.scanResult.findings,
            newConfigs,
            skippedCount,
            skippedUnsupportedCount,
          });
          return;
        }
        finishImport(configsToImport, batchGate.scanResults, newConfigs, {
          skippedCount,
          skippedUnsupportedCount,
        });
        return;
      }

      toast({
        title: t('mcpImportSuccess'),
        description: t('mcpImportSkipped', { count: skippedCount }),
      });
    } catch (e) {
      setImportError(t('mcpImportParseError') + (e instanceof Error ? `: ${e.message}` : ''));
    }
  }, [importJsonText, mcpConfig, finishImport, t, toast]);

  return (
    <div className="flex flex-col space-y-4">
      {/* 配置列表 */}
      <MCPConfigList
        configs={mcpConfig.configs}
        mcpStatus={mcpConfig.mcpStatus}
        togglingIndex={mcpConfig.togglingIndex}
        onAddConfig={mcpConfig.handleAddConfig}
        onEditConfig={mcpConfig.handleEditConfig}
        onToggleConfig={mcpConfig.handleToggleConfig}
        onDeleteConfirm={(index) => mcpConfig.setDeleteConfirmIndex(index)}
        onShowImport={() => mcpConfig.setShowImportModal(true)}
      />

      {/* 配置编辑弹窗 */}
      <MCPConfigEditor
        show={mcpConfig.showConfigModal}
        editingIndex={mcpConfig.editingIndex}
        formData={mcpConfig.formData}
        rawArgsInput={mcpConfig.rawArgsInput}
        errors={mcpConfig.errors}
        isValidating={mcpConfig.isValidating}
        validationSuccess={mcpConfig.validationSuccess}
        validationError={mcpConfig.validationError}
        validationLatency={mcpConfig.validationLatency}
        scanFindings={mcpConfig.scanFindings}
        isLiveScanning={mcpConfig.isLiveScanning}
        connectionTypeOptions={mcpConfig.connectionTypeOptions}
        pendingDescriptionChoice={mcpConfig.pendingDescriptionChoice}
        onFormDataChange={mcpConfig.setFormData}
        onRawArgsInputChange={mcpConfig.setRawArgsInput}
        onSave={mcpConfig.handleSaveConfig}
        onCancel={mcpConfig.resetForm}
        onConfirmDescription={mcpConfig.handleConfirmDescription}
        onCancelDescriptionChoice={mcpConfig.handleCancelDescriptionChoice}
      />

      {/* JSON 导入弹窗 */}
      <MCPJsonImporter
        show={mcpConfig.showImportModal}
        importJsonText={importJsonText}
        importError={importError}
        importPlaceholder={mcpConfig.importPlaceholder}
        supportsStdio={mcpConfig.supportsStdio}
        onImportJsonTextChange={(value) => {
          setImportJsonText(value);
          setImportError('');
        }}
        onImport={handleImportJson}
        onCancel={() => {
          mcpConfig.setShowImportModal(false);
          setImportJsonText('');
          setImportError('');
        }}
      />

      <MCPScanAckDialog
        open={!!mcpConfig.pendingRiskAck}
        serverName={mcpConfig.pendingRiskAck?.finalFormData.name || ''}
        findings={mcpConfig.pendingRiskAck?.scanResult.findings ?? []}
        onConfirm={mcpConfig.handleConfirmRiskAck}
        onCancel={mcpConfig.handleCancelRiskAck}
      />

      <MCPScanAckDialog
        open={!!mcpConfig.pendingToggleAck}
        serverName={mcpConfig.configs[mcpConfig.pendingToggleAck?.index ?? -1]?.name || ''}
        findings={mcpConfig.pendingToggleAck?.scanResult.findings ?? []}
        onConfirm={mcpConfig.handleConfirmToggleAck}
        onCancel={mcpConfig.handleCancelToggleAck}
      />

      <MCPScanAckDialog
        open={!!pendingImportAck}
        serverName={pendingImportAck?.ackServerName || ''}
        findings={pendingImportAck?.ackFindings ?? []}
        onConfirm={handleConfirmImportAck}
        onCancel={() => setPendingImportAck(null)}
      />

      {/* 删除确认对话框 */}
      <DeleteConfirmDialog
        show={mcpConfig.deleteConfirmIndex !== null}
        configName={
          mcpConfig.deleteConfirmIndex !== null ? mcpConfig.configs[mcpConfig.deleteConfirmIndex]?.name || '' : ''
        }
        onConfirm={() => {
          if (mcpConfig.deleteConfirmIndex !== null) {
            mcpConfig.handleDeleteConfig(mcpConfig.deleteConfirmIndex);
          }
        }}
        onCancel={mcpConfig.handleDeleteCancel}
      />
    </div>
  );
};

export default MCPConfigForm;
