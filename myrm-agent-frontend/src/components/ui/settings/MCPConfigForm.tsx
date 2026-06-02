import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { MCPServiceConfig } from '@/store/useConfigStore';
import { useMCPConfig } from '@/hooks/useMCPConfig';
import { MCPConfigList } from './mcp/MCPConfigList';
import { MCPConfigEditor } from './mcp/MCPConfigEditor';
import { MCPJsonImporter } from './mcp/MCPJsonImporter';
import { DeleteConfirmDialog } from './mcp/DeleteConfirmDialog';
import { useToast } from '@/hooks/useToast';
import { parseMCPConfigsFromJSON } from '@/utils/mcpConfigParser';

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

  // 使用自定义Hook管理所有状态和逻辑
  const mcpConfig = useMCPConfig(currentConfigs, onSave);

  // JSON导入处理（保留在主组件，因为逻辑复杂且依赖多个状态）
  const handleImportJson = useCallback(() => {
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
      let addedCount = 0;
      let skippedCount = 0;
      let disabledCount = 0;

      for (const importedConfig of filteredConfigs) {
        if (existingNames.has(importedConfig.name)) {
          skippedCount++;
          continue;
        }
        const needsDescription = !importedConfig.description.trim();
        if (needsDescription) {
          importedConfig.enabled = false;
          disabledCount++;
        }
        newConfigs.push(importedConfig);
        existingNames.add(importedConfig.name);
        addedCount++;
      }

      mcpConfig.setConfigs(newConfigs);
      onSave(newConfigs);
      mcpConfig.setShowImportModal(false);
      setImportJsonText('');

      const parts: string[] = [t('mcpImportSuccessDesc', { count: addedCount })];
      if (skippedCount > 0) parts.push(t('mcpImportSkipped', { count: skippedCount }));
      if (skippedUnsupportedCount > 0) parts.push(t('mcpImportUnsupportedSkipped', { count: skippedUnsupportedCount }));
      if (disabledCount > 0) parts.push(t('mcpImportDisabledNoDesc', { count: disabledCount }));

      toast({
        title: t('mcpImportSuccess'),
        description: parts.join(' · '),
      });
    } catch (e) {
      setImportError(t('mcpImportParseError') + (e instanceof Error ? `: ${e.message}` : ''));
    }
  }, [importJsonText, mcpConfig, onSave, t, toast]);

  return (
    <div className="flex flex-col space-y-4">
      {/* 配置列表 */}
      <MCPConfigList
        configs={mcpConfig.configs}
        mcpStatus={mcpConfig.mcpStatus}
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
