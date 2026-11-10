'use client';

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Wand2, Plug, FileText, Wrench, Globe } from 'lucide-react';
import type { Skill } from '@/store/skill/types';
import type { AgentSkillConfigMap } from '@/types/agentSkillConfig';
import type { MCPServiceConfig } from '@/store/config/types';
import type { BuiltinToolId } from '@/store/chat/types';
import type { AgentConfig } from '@/store/chat/types/sessionConfig';
import { useFeatureEntitlements } from '@/hooks/billing/useFeatureEntitlements';
import { isLocalMode, isSandbox } from '@/lib/deploy-mode';
import { stripEntitlementBlockedBuiltinTools } from '@/lib/builtin-tool-entitlements';
import type { ConfigCardType } from './AgentConfigCards';
import { ActionSpaceAccuracyRadar } from './ActionSpaceAccuracyRadar';
import { SkillsSectionPanel } from './SkillsSectionPanel';
import { McpServersPanel } from './McpServersPanel';
import { BuiltinToolsPanel } from './BuiltinToolsPanel';
import { SubagentsPanel } from './SubagentsPanel';
import { InstructionPanel } from './InstructionPanel';
import type { EphemeralSubagentConfig } from './SubagentCard';
import { useActionSpaceRadar } from './useActionSpaceRadar';
import { useInstructionAssist } from './useInstructionAssist';

export type SettingsSheetType = 'skills' | 'mcp';

/** 面板在打开弹窗那一刻交给编辑器的设置；缺省项按“没配置过”处理。 */
export interface ConfigEditorProps {
  type: ConfigCardType;
  agentId?: string;
  enabledSkills: Skill[];
  enabledMcps: MCPServiceConfig[];
  selectedSkillIds?: string[];
  skillConfigs?: AgentSkillConfigMap;
  selectedMcpNames?: string[];
  mcpToolSelections?: Record<string, string[]>;
  systemPrompt?: string;
  useGlobalInstruction?: boolean;
  autoRestoreDomains?: string[];
  enabledBuiltinTools: BuiltinToolId[];
  browserSource?: string;
  dialogPolicy?: AgentConfig['dialogPolicy'];
  sessionRecording?: AgentConfig['sessionRecording'];
  ephemeralSubagents?: Record<string, unknown>;
  isSystemPromptHidden?: boolean;
  loadingSystemPrompt?: boolean;
  onShowSystemPrompt?: () => void;
  onRefreshSkills?: () => Promise<void>;
  onSave: (data: Partial<AgentConfig>) => void;
}

interface ConfigEditorInternalProps extends ConfigEditorProps {
  onClose: () => void;
  onOpenSettingsSheet: (type: SettingsSheetType) => void;
}

/**
 * 编辑弹窗里的表单：草稿在挂载时取自传入的设置，之后只由用户的编辑改变。
 * 弹窗每次打开都会重新挂载它，所以草稿总是打开那一刻的设置，关闭后的未保存修改不会留下。
 */
export const ConfigEditor = ({
  type,
  agentId,
  enabledSkills,
  enabledMcps,
  selectedSkillIds,
  skillConfigs,
  selectedMcpNames,
  mcpToolSelections,
  systemPrompt,
  useGlobalInstruction,
  autoRestoreDomains,
  enabledBuiltinTools,
  browserSource,
  dialogPolicy,
  sessionRecording,
  ephemeralSubagents,
  isSystemPromptHidden = false,
  loadingSystemPrompt = false,
  onShowSystemPrompt,
  onRefreshSkills,
  onSave,
  onClose,
  onOpenSettingsSheet,
}: ConfigEditorInternalProps) => {
  const t = useTranslations('agent.configEditor');
  const tAgent = useTranslations('agent');
  const tPanel = useTranslations('agent.configPanel');
  const tCommon = useTranslations('common');
  const { canUseCron, canUseVnc, isLoading: entitlementsLoading } = useFeatureEntitlements();
  const sandboxMode = isSandbox();

  const [localSkillIds, setLocalSkillIds] = useState<string[]>(selectedSkillIds ?? []);
  const [localSkillConfigs, setLocalSkillConfigs] = useState<AgentSkillConfigMap>(skillConfigs ?? {});
  const [localMcpNames, setLocalMcpNames] = useState<string[]>(selectedMcpNames ?? []);
  const [localMcpToolSelections, setLocalMcpToolSelections] = useState<Record<string, string[]>>(
    mcpToolSelections ?? {},
  );
  const [localPrompt, setLocalPrompt] = useState(systemPrompt ?? '');
  const [localUseGlobalInstruction, setLocalUseGlobalInstruction] = useState(useGlobalInstruction ?? true);
  const [localAutoRestoreDomains, setLocalAutoRestoreDomains] = useState<string[]>(autoRestoreDomains ?? []);
  const [pickedBuiltinTools, setPickedBuiltinTools] = useState<BuiltinToolId[]>(enabledBuiltinTools);
  const [localBrowserSource, setLocalBrowserSource] = useState(browserSource);
  const [localDialogPolicy, setLocalDialogPolicy] = useState(dialogPolicy);
  const [localSessionRecording, setLocalSessionRecording] = useState(sessionRecording);
  const [localEphemeralSubagents, setLocalEphemeralSubagents] = useState(
    (ephemeralSubagents ?? {}) as Record<string, EphemeralSubagentConfig>,
  );
  const [displayNameErrors, setDisplayNameErrors] = useState<Record<string, string>>({});
  const [externalCliBackendReady, setExternalCliBackendReady] = useState<boolean | null>(null);

  // 沙箱里套餐不含的工具不能保存：权益加载完成后从草稿里去掉，加载期间如实显示。
  const localBuiltinTools = useMemo(
    () =>
      sandboxMode && !entitlementsLoading
        ? stripEntitlementBlockedBuiltinTools(pickedBuiltinTools, { sandbox: sandboxMode, canUseCron, canUseVnc })
        : pickedBuiltinTools,
    [pickedBuiltinTools, sandboxMode, entitlementsLoading, canUseCron, canUseVnc],
  );

  // 本地模式下启用外部 CLI 必须先有可用后端；原因由内置工具面板就地说明，这里只禁用确认。
  const externalCliSaveBlocked =
    type === 'builtin_tools' &&
    isLocalMode() &&
    localBuiltinTools.includes('external_cli') &&
    externalCliBackendReady !== true;

  const assist = useInstructionAssist({
    active: type === 'instruction',
    agentId,
    prompt: localPrompt,
    setPrompt: setLocalPrompt,
  });
  const radar = useActionSpaceRadar({
    estimate: type !== 'instruction',
    enabledSkills,
    skillIds: localSkillIds,
    skillConfigs: localSkillConfigs,
    mcpNames: localMcpNames,
    builtinTools: localBuiltinTools,
    onRefreshSkills,
  });

  const toggleMcp = (name: string) => {
    setLocalMcpNames((prev) => (prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]));
  };
  const handleMcpToolSelectionChange = useCallback((serverName: string, tools: string[] | undefined) => {
    setLocalMcpToolSelections((prev) => {
      if (!tools) {
        const { [serverName]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [serverName]: tools };
    });
  }, []);

  const handleSave = () => {
    if (type === 'subagents' && Object.values(displayNameErrors).some((e) => e !== '')) {
      return;
    }
    switch (type) {
      case 'skills':
        onSave({ selectedSkillIds: localSkillIds, skillConfigs: localSkillConfigs });
        break;
      case 'mcp':
        onSave({
          selectedMcpNames: localMcpNames,
          mcpToolSelections: Object.keys(localMcpToolSelections).length > 0 ? localMcpToolSelections : undefined,
        });
        break;
      case 'instruction':
        onSave({ systemPrompt: localPrompt, useGlobalInstruction: localUseGlobalInstruction });
        break;
      case 'builtin_tools':
        onSave({
          enabledBuiltinTools: localBuiltinTools,
          autoRestoreDomains: localAutoRestoreDomains,
          browserSource: localBrowserSource,
          dialogPolicy: localDialogPolicy,
          sessionRecording: localSessionRecording,
        });
        break;
      case 'subagents':
        onSave({ ephemeralSubagents: localEphemeralSubagents });
        break;
    }
    onClose();
  };

  const getDialogConfig = () => {
    switch (type) {
      case 'skills':
        return {
          icon: <Wand2 size={20} className="text-blue-500" />,
          title: t('skillsSection'),
          description: t('skillsSectionDesc'),
        };
      case 'mcp':
        return {
          icon: <Plug size={20} className="text-purple-500" />,
          title: t('mcpSection'),
          description: t('mcpSectionDesc'),
        };
      case 'builtin_tools':
        return {
          icon: <Wrench size={20} className="text-orange-500" />,
          title: t('builtinToolsSection'),
          description: t('builtinToolsSectionDesc'),
        };
      case 'subagents':
        return {
          icon: <Globe size={20} className="text-green-500" />,
          title: t('subagentsSection'),
          description: t('subagentsSectionDesc'),
        };
      case 'instruction':
        return {
          icon: <FileText size={20} className="text-amber-500" />,
          title: t('instructionSection'),
          description: '',
        };
    }
  };

  const renderContent = () => {
    switch (type) {
      case 'skills':
        return (
          <SkillsSectionPanel
            enabledSkills={enabledSkills}
            agentId={agentId}
            localSkillIds={localSkillIds}
            setLocalSkillIds={setLocalSkillIds}
            localSkillConfigs={localSkillConfigs}
            setLocalSkillConfigs={setLocalSkillConfigs}
            noiseData={{
              isNoiseHigh: radar.isNoiseHigh,
              isNoiseCritical: radar.isNoiseCritical,
              noiseLevel: radar.noiseLevel,
              actionSpaceScore: radar.actionSpaceScore,
              maxSafeScore: radar.maxSafeScore,
            }}
            staleCoreSkills={radar.staleCoreSkills}
            isSmartPruning={radar.isSmartPruning}
            onSmartPrune={radar.handleSmartPrune}
            onOpenSettingsSheet={onOpenSettingsSheet}
            t={t}
            tPanel={tPanel}
          />
        );
      case 'mcp':
        return (
          <McpServersPanel
            enabledMcps={enabledMcps}
            selectedNames={localMcpNames}
            toolSelections={localMcpToolSelections}
            onToggle={toggleMcp}
            onToolSelectionChange={handleMcpToolSelectionChange}
            onAddMore={() => onOpenSettingsSheet('mcp')}
          />
        );
      case 'builtin_tools':
        return (
          <BuiltinToolsPanel
            localBuiltinTools={localBuiltinTools}
            setLocalBuiltinTools={setPickedBuiltinTools}
            localAutoRestoreDomains={localAutoRestoreDomains}
            setLocalAutoRestoreDomains={setLocalAutoRestoreDomains}
            localBrowserSource={localBrowserSource}
            setLocalBrowserSource={setLocalBrowserSource}
            localDialogPolicy={localDialogPolicy}
            setLocalDialogPolicy={setLocalDialogPolicy}
            localSessionRecording={localSessionRecording}
            setLocalSessionRecording={setLocalSessionRecording}
            onExternalCliBackendReady={setExternalCliBackendReady}
            t={t}
            tAgent={tAgent}
            tPanel={tPanel}
          />
        );
      case 'subagents':
        return (
          <SubagentsPanel
            localEphemeralSubagents={localEphemeralSubagents}
            setLocalEphemeralSubagents={setLocalEphemeralSubagents}
            t={t}
            tCommon={tCommon}
            displayNameErrors={displayNameErrors}
            setDisplayNameErrors={setDisplayNameErrors}
          />
        );
      case 'instruction':
        return (
          <InstructionPanel
            localPrompt={localPrompt}
            setLocalPrompt={setLocalPrompt}
            localUseGlobalInstruction={localUseGlobalInstruction}
            setLocalUseGlobalInstruction={setLocalUseGlobalInstruction}
            isSystemPromptHidden={isSystemPromptHidden}
            loadingSystemPrompt={loadingSystemPrompt}
            onShowSystemPrompt={onShowSystemPrompt}
            onAiGenerate={assist.handleAiGenerate}
            isGeneratingAi={assist.isGeneratingAi}
            history={assist.history}
            t={t}
            tCommon={tCommon}
          />
        );
    }
  };

  const config = getDialogConfig();

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          {config.icon}
          {config.title}
        </DialogTitle>
        {config.description && <p className="text-sm text-muted-foreground mt-1">{config.description}</p>}
      </DialogHeader>

      <div className="py-4">
        {type !== 'instruction' && (
          <ActionSpaceAccuracyRadar
            isEvaluating={radar.isEvaluating}
            accuracyLevel={radar.accuracyLevel}
            isNoiseHigh={radar.isNoiseHigh}
            isNoiseCritical={radar.isNoiseCritical}
            staleCoreSkillCount={radar.staleCoreSkills.length}
            isSmartPruning={radar.isSmartPruning}
            onSmartPrune={radar.handleSmartPrune}
            catalogPreview={radar.catalogPreview}
            showTurn1Catalog={type === 'skills'}
          />
        )}
        {renderContent()}
      </div>

      <DialogFooter className="gap-2 sm:gap-0">
        <Button variant="outline" onClick={onClose}>
          {tCommon('cancel')}
        </Button>
        <Button onClick={handleSave} disabled={externalCliSaveBlocked}>
          {tCommon('confirm')}
        </Button>
      </DialogFooter>
    </>
  );
};
