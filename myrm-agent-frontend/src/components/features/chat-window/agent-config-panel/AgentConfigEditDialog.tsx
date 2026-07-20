'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { Button } from '@/components/primitives/button';
import { Skill } from '@/store/skill/types';
import { MCPServiceConfig } from '@/store/config/types';
import { type BuiltinToolId } from '@/store/chat/types';
import { type AgentThemeColor } from '@/components/features/message-box/progress-steps/toolIcons';
import { Wand2, Plug, FileText, Wrench, Globe, Search, X } from 'lucide-react';
import { getApiUrl } from '@/lib/api';
import { Input } from '@/components/primitives/input';
import { toast } from '@/hooks/useToast';
import { runCuratorSweep } from '@/services/skill';
import type { ConfigCardType } from './AgentConfigCards';
import { ActionSpaceAccuracyRadar } from './ActionSpaceAccuracyRadar';
import { AddMoreButton, SelectableCard } from './AgentConfigSelectableCard';
import { SkillsSectionPanel } from './SkillsSectionPanel';
import { BuiltinToolsPanel } from './BuiltinToolsPanel';
import { SubagentsPanel } from './SubagentsPanel';
import { InstructionPanel } from './InstructionPanel';
import { useFeatureEntitlements } from '@/hooks/useFeatureEntitlements';
import { isSandbox } from '@/lib/deploy-mode';
import { stripEntitlementBlockedBuiltinTools } from '@/lib/builtin-tool-entitlements';
import dynamic from 'next/dynamic';

type EphemeralSubagentConfig = {
  display_name?: string;
  theme_color?: AgentThemeColor;
  control_scope?: 'leaf' | 'orchestrator';
};

const EMPTY_AUTO_RESTORE_DOMAINS: string[] = [];
const EMPTY_SKILL_CONFIGS: Record<string, { is_core?: boolean }> = {};
const EMPTY_EPHEMERAL_SUBAGENTS: Record<string, EphemeralSubagentConfig> = {};

const MCPToolSelector = dynamic(() => import('./MCPToolSelector'), { ssr: false });
const SkillsSection = dynamic(() => import('@/components/features/settings/sections/ai-tools/SkillsSection'), { ssr: false });
const MCPSection = dynamic(() => import('@/components/features/settings/sections/ai-tools/MCPSection'), { ssr: false });

interface AgentConfigEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  type: ConfigCardType;
  agentId?: string;
  enabledSkills: Skill[];
  enabledMcps: MCPServiceConfig[];
  selectedSkillIds: string[];
  mountedSkillIds?: string[];
  skillConfigs?: Record<string, { is_core?: boolean }>;
  selectedMcpNames: string[];
  mcpToolSelections?: Record<string, string[]>;
  systemPrompt: string;
  useGlobalInstruction: boolean;
  autoRestoreDomains?: string[];
  enabledBuiltinTools: BuiltinToolId[];
  browserSource?: string;
  dialogPolicy?: string;
  sessionRecording?: string;
  ephemeralSubagents?: Record<string, unknown>;
  isSystemPromptHidden?: boolean;
  loadingSystemPrompt?: boolean;
  onShowSystemPrompt?: () => void;
  onRefreshSkills?: () => Promise<void>;
  onSave: (data: {
    selectedSkillIds?: string[];
    mountedSkillIds?: string[];
    skillConfigs?: Record<string, { is_core?: boolean }>;
    selectedMcpNames?: string[];
    mcpToolSelections?: Record<string, string[]>;
    systemPrompt?: string;
    useGlobalInstruction?: boolean;
    enabledBuiltinTools?: BuiltinToolId[];
    browserSource?: string;
    dialogPolicy?: string;
    sessionRecording?: string;
    autoRestoreDomains?: string[];
    ephemeralSubagents?: Record<string, unknown>;
    personalityStyle?: string;
  }) => void;
}

const AgentConfigEditDialog = ({
  open,
  onOpenChange,
  type,
  agentId,
  enabledSkills,
  enabledMcps,
  selectedSkillIds: initialSkillIds,
  mountedSkillIds: initialMountedSkillIds,
  skillConfigs: initialSkillConfigs = EMPTY_SKILL_CONFIGS,
  selectedMcpNames: initialMcpNames,
  mcpToolSelections: initialMcpToolSelections,
  systemPrompt: initialPrompt,
  useGlobalInstruction: initialUseGlobalInstruction,
  autoRestoreDomains: initialAutoRestoreDomains = EMPTY_AUTO_RESTORE_DOMAINS,
  enabledBuiltinTools: initialBuiltinTools,
  browserSource: initialBrowserSource,
  dialogPolicy: initialDialogPolicy,
  sessionRecording: initialSessionRecording,
  ephemeralSubagents: initialEphemeralSubagents = EMPTY_EPHEMERAL_SUBAGENTS,
  isSystemPromptHidden = false,
  loadingSystemPrompt = false,
  onShowSystemPrompt,
  onRefreshSkills,
  onSave,
}: AgentConfigEditDialogProps) => {
  const t = useTranslations('agent.configEditor');
  const tAgent = useTranslations('agent');
  const tPanel = useTranslations('agent.configPanel');
  const tCommon = useTranslations('common');
  const { canUseCron, canUseVnc, isLoading: entitlementsLoading } = useFeatureEntitlements();
  const sandboxMode = isSandbox();

  const entitlementBuiltinToolsOptions = useMemo(
    () => ({
      sandbox: sandboxMode,
      canUseCron,
      canUseVnc,
    }),
    [sandboxMode, canUseCron, canUseVnc],
  );

  /* ─── local state ─── */
  const [localSkillIds, setLocalSkillIds] = useState<string[]>(initialSkillIds || []);
  const [localMountedSkillIds, setLocalMountedSkillIds] = useState<string[]>(initialMountedSkillIds || []);
  const [localSkillConfigs, setLocalSkillConfigs] = useState<Record<string, { is_core?: boolean }>>(initialSkillConfigs || {});
  const [localMcpNames, setLocalMcpNames] = useState<string[]>(initialMcpNames || []);
  const [localMcpToolSelections, setLocalMcpToolSelections] = useState<Record<string, string[]>>(initialMcpToolSelections || {});
  const [localPrompt, setLocalPrompt] = useState(initialPrompt || '');
  const [localUseGlobalInstruction, setLocalUseGlobalInstruction] = useState(initialUseGlobalInstruction ?? true);
  const [localAutoRestoreDomains, setLocalAutoRestoreDomains] = useState<string[]>(initialAutoRestoreDomains || []);
  const [localBuiltinTools, setLocalBuiltinTools] = useState<BuiltinToolId[]>(initialBuiltinTools || []);
  const [localBrowserSource, setLocalBrowserSource] = useState<string | undefined>(initialBrowserSource);
  const [localDialogPolicy, setLocalDialogPolicy] = useState<string | undefined>(initialDialogPolicy);
  const [localSessionRecording, setLocalSessionRecording] = useState<string | undefined>(initialSessionRecording);
  const [localEphemeralSubagents, setLocalEphemeralSubagents] = useState<Record<string, EphemeralSubagentConfig>>(
    initialEphemeralSubagents as Record<string, EphemeralSubagentConfig>,
  );
  const [displayNameErrors, setDisplayNameErrors] = useState<Record<string, string>>({});
  const [mcpSearchQuery, setMcpSearchQuery] = useState('');

  /* ─── settings sheet ─── */
  const [settingsSheetOpen, setSettingsSheetOpen] = useState(false);
  const [settingsSheetType, setSettingsSheetType] = useState<'skills' | 'mcp' | null>(null);

  /* ─── AI generation ─── */
  const [isGeneratingAi, setIsGeneratingAi] = useState(false);
  const [isSmartPruning, setIsSmartPruning] = useState(false);
  const [history, setHistory] = useState<Array<{ id: string; version: number; systemPrompt: string; createdAt: string }>>([]);

  /* ─── sync on open ─── */
  useEffect(() => {
    if (open) {
      setLocalSkillIds(initialSkillIds || []);
      setLocalMountedSkillIds(initialMountedSkillIds || []);
      setLocalSkillConfigs(initialSkillConfigs || {});
      setLocalMcpNames(initialMcpNames || []);
      setLocalPrompt(initialPrompt || '');
      setLocalUseGlobalInstruction(initialUseGlobalInstruction ?? true);
      setLocalAutoRestoreDomains(initialAutoRestoreDomains || []);
      setLocalBuiltinTools(initialBuiltinTools || []);
      setLocalBrowserSource(initialBrowserSource);
      setLocalEphemeralSubagents(initialEphemeralSubagents as Record<string, EphemeralSubagentConfig>);
      setMcpSearchQuery('');
      setDisplayNameErrors({});
    }
  }, [
    open, initialSkillIds, initialMountedSkillIds, initialSkillConfigs,
    initialMcpNames, initialPrompt, initialUseGlobalInstruction,
    initialAutoRestoreDomains, initialBuiltinTools, initialEphemeralSubagents,
  ]);

  useEffect(() => {
    if (!open || !sandboxMode || entitlementsLoading) {
      return;
    }
    setLocalBuiltinTools((prev) => stripEntitlementBlockedBuiltinTools(prev, entitlementBuiltinToolsOptions));
  }, [open, sandboxMode, entitlementsLoading, entitlementBuiltinToolsOptions]);

  /* ─── fetch history ─── */
  useEffect(() => {
    if (open && type === 'instruction' && agentId) {
      fetch(getApiUrl(`/user-agents/${agentId}/history`))
        .then((res) => res.json())
        .then((data) => { if (data.data) setHistory(data.data); })
        .catch((err) => console.error('Failed to fetch history:', err));
    }
  }, [open, type, agentId]);

  /* ─── AI prompt generation (streaming) ─── */
  const handleAiGenerate = useCallback(async (intent: string) => {
    if (!intent.trim()) return;
    setIsGeneratingAi(true);
    const currentPrompt = localPrompt;
    try {
      const response = await fetch(getApiUrl('/user-agents/generate-prompt'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent, locale: navigator.language || 'en-US', current_prompt: currentPrompt }),
      });
      if (!response.ok) {
        if (response.status === 422) {
          const errorData = await response.json();
          toast({ title: t('aiGenerateConfigMissing'), description: typeof errorData.detail === 'string' ? errorData.detail : undefined, variant: 'destructive' });
          return;
        }
        throw new Error('Failed to generate prompt');
      }
      if (!response.body) throw new Error('No response body');
      let isFirstChunk = true;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'content' && data.data) {
                if (isFirstChunk) { setLocalPrompt(''); isFirstChunk = false; }
                setLocalPrompt((prev) => prev + data.data);
              } else if (data.type === 'error') {
                toast({ title: t('aiGenerateFailed'), description: typeof data.error === 'string' ? data.error : undefined, variant: 'destructive' });
              }
            } catch (e) { console.error('Failed to parse SSE chunk', e); }
          }
        }
      }
    } catch (error) { console.error('Failed to generate AI prompt:', error); }
    finally { setIsGeneratingAi(false); }
  }, [localPrompt, t]);

  /* ─── action space evaluation ─── */
  const [accuracyData, setAccuracyData] = useState({ accuracyLevel: 100, actionSpaceScore: 0, maxSafeScore: 1500, isNoiseHigh: false, isNoiseCritical: false });
  const [isEvaluating, setIsEvaluating] = useState(false);

  useEffect(() => {
    setIsEvaluating(true);
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(getApiUrl('/user-agents/evaluate-action-space'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ skill_ids: localSkillIds, skill_configs: localSkillConfigs, mcp_servers: localMcpNames, enabled_builtin_tools: localBuiltinTools }),
        });
        if (response.ok) {
          const resData = await response.json();
          if (resData.data) {
            setAccuracyData({
              accuracyLevel: resData.data.accuracy_level,
              actionSpaceScore: resData.data.ascs_score,
              maxSafeScore: resData.data.max_safe_score,
              isNoiseHigh: resData.data.is_high,
              isNoiseCritical: resData.data.is_critical,
            });
          }
        }
      } catch (e) { console.error('Failed to evaluate action space', e); }
      finally { setIsEvaluating(false); }
    }, 500);
    return () => clearTimeout(timer);
  }, [localSkillIds, localSkillConfigs, localMcpNames, localBuiltinTools]);

  const { accuracyLevel, actionSpaceScore, maxSafeScore, isNoiseHigh, isNoiseCritical } = accuracyData;
  const noiseLevel = Math.min(100, Math.round((actionSpaceScore / maxSafeScore) * 100));

  const staleCoreSkills = useMemo(() => {
    return localSkillIds.filter((id) => {
      const isCore = localSkillConfigs?.[id]?.is_core ?? true;
      if (!isCore) return false;
      const skill = enabledSkills?.find((s) => s.id === id);
      return skill?.usage_stats?.lifecycle_status === 'stale';
    });
  }, [localSkillIds, localSkillConfigs, enabledSkills]);

  const handleSmartPrune = useCallback(async () => {
    if (isSmartPruning) return;
    setIsSmartPruning(true);
    try {
      toast({ title: tPanel('actionSpaceRadar.smartPruneRunning') });
      const result = await runCuratorSweep();
      toast({
        title: tPanel('actionSpaceRadar.smartPruneSuccess', {
          stale: result.stale_count,
          archived: result.archived_count,
        }),
      });
      if (onRefreshSkills) {
        await onRefreshSkills();
      }
    } catch (error) {
      console.error('Curator sweep failed', error);
      toast({ title: tPanel('actionSpaceRadar.smartPruneFailed'), variant: 'destructive' });
    } finally {
      setIsSmartPruning(false);
    }
  }, [isSmartPruning, onRefreshSkills, tPanel]);

  /* ─── save handler ─── */
  const handleSave = useCallback(() => {
    if (type === 'subagents') {
      if (Object.values(displayNameErrors).some((e) => e !== '')) return;
    }
    switch (type) {
      case 'skills':
        onSave({ selectedSkillIds: localSkillIds, mountedSkillIds: localMountedSkillIds, skillConfigs: localSkillConfigs });
        break;
      case 'mcp':
        onSave({ selectedMcpNames: localMcpNames, mcpToolSelections: Object.keys(localMcpToolSelections).length > 0 ? localMcpToolSelections : undefined });
        break;
      case 'instruction':
        onSave({ systemPrompt: localPrompt, useGlobalInstruction: localUseGlobalInstruction });
        break;
      case 'builtin_tools':
        onSave({ enabledBuiltinTools: localBuiltinTools, autoRestoreDomains: localAutoRestoreDomains, browserSource: localBrowserSource, dialogPolicy: localDialogPolicy, sessionRecording: localSessionRecording });
        break;
      case 'subagents':
        onSave({ ephemeralSubagents: localEphemeralSubagents });
        break;
    }
    onOpenChange(false);
  }, [type, localSkillIds, localSkillConfigs, localMcpNames, localPrompt, localUseGlobalInstruction, localBuiltinTools, localEphemeralSubagents, displayNameErrors, onSave, onOpenChange]);

  /* ─── dialog config ─── */
  const getDialogConfig = () => {
    switch (type) {
      case 'skills': return { icon: <Wand2 size={20} className="text-blue-500" />, title: t('skillsSection'), description: t('skillsSectionDesc') };
      case 'mcp': return { icon: <Plug size={20} className="text-purple-500" />, title: t('mcpSection'), description: t('mcpSectionDesc') };
      case 'builtin_tools': return { icon: <Wrench size={20} className="text-orange-500" />, title: t('builtinToolsSection'), description: t('builtinToolsSectionDesc') };
      case 'subagents': return { icon: <Globe size={20} className="text-green-500" />, title: t('subagentsSection'), description: t('subagentsSectionDesc') };
      case 'instruction': return { icon: <FileText size={20} className="text-amber-500" />, title: t('instructionSection'), description: '' };
    }
  };

  const config = getDialogConfig();

  /* ─── mcp ─── */
  const filteredMcps = (enabledMcps || []).filter((m) => m.name.toLowerCase().includes(mcpSearchQuery.toLowerCase()));
  const toggleMcp = (name: string) => { setLocalMcpNames((prev) => (prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name])); };
  const handleMcpToolSelectionChange = useCallback((serverName: string, tools: string[] | undefined) => {
    setLocalMcpToolSelections((prev) => {
      if (!tools) { const { [serverName]: _, ...rest } = prev; return rest; }
      return { ...prev, [serverName]: tools };
    });
  }, []);

  const handleOpenSettingsSheet = useCallback((sheetType: 'skills' | 'mcp') => {
    setSettingsSheetType(sheetType);
    setSettingsSheetOpen(true);
  }, []);

  /* ─── render content by type ─── */
  const renderContent = () => {
    switch (type) {
      case 'skills':
        return (
          <SkillsSectionPanel
            enabledSkills={enabledSkills}
            agentId={agentId}
            localSkillIds={localSkillIds}
            setLocalSkillIds={setLocalSkillIds}
            localMountedSkillIds={localMountedSkillIds}
            setLocalMountedSkillIds={setLocalMountedSkillIds}
            localSkillConfigs={localSkillConfigs}
            setLocalSkillConfigs={setLocalSkillConfigs}
            noiseData={{ isNoiseHigh, isNoiseCritical, noiseLevel, coreSkillsTokenCost: actionSpaceScore, maxCoreTokens: maxSafeScore }}
            staleCoreSkills={staleCoreSkills}
            isSmartPruning={isSmartPruning}
            onSmartPrune={handleSmartPrune}
            onOpenSettingsSheet={handleOpenSettingsSheet}
            t={t}
            tPanel={tPanel}
          />
        );

      case 'mcp':
        return (
          <div className="space-y-4">
            {enabledMcps.length > 0 && (
              <>
                <div className="relative">
                  <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
                  <Input
                    value={mcpSearchQuery}
                    onChange={(e) => setMcpSearchQuery(e.target.value)}
                    placeholder={t('searchPlaceholder')}
                    className="pl-10 h-10 bg-muted/40 border-0 rounded-xl placeholder:text-muted-foreground/50 focus:bg-muted/60 transition-colors"
                  />
                </div>
                <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                  {filteredMcps.map((mcp) => {
                    const isEnabled = localMcpNames.includes(mcp.name);
                    return (
                      <div key={mcp.name}>
                        <SelectableCard
                          id={`mcp-${mcp.name}`}
                          label={mcp.name}
                          description={mcp.description || mcp.type}
                          checked={isEnabled}
                          onCheckedChange={() => toggleMcp(mcp.name)}
                          icon={<Plug size={14} />}
                          colorClass="text-purple-500"
                        />
                        <MCPToolSelector
                          mcpConfig={mcp}
                          serverName={mcp.name}
                          selectedTools={localMcpToolSelections[mcp.name]}
                          onSelectionChange={handleMcpToolSelectionChange}
                          isServerEnabled={isEnabled}
                        />
                      </div>
                    );
                  })}
                </div>
              </>
            )}
            {enabledMcps.length === 0 && (
              <div className="py-6 text-center">
                <p className="text-sm text-muted-foreground mb-3">{t('noEnabledMcp')}</p>
              </div>
            )}
            <AddMoreButton label={t('addMore')} onClick={() => handleOpenSettingsSheet('mcp')} />
          </div>
        );

      case 'builtin_tools':
        return (
          <BuiltinToolsPanel
            localBuiltinTools={localBuiltinTools}
            setLocalBuiltinTools={setLocalBuiltinTools}
            localAutoRestoreDomains={localAutoRestoreDomains}
            setLocalAutoRestoreDomains={setLocalAutoRestoreDomains}
            localBrowserSource={localBrowserSource}
            setLocalBrowserSource={setLocalBrowserSource}
            localDialogPolicy={localDialogPolicy}
            setLocalDialogPolicy={setLocalDialogPolicy}
            localSessionRecording={localSessionRecording}
            setLocalSessionRecording={setLocalSessionRecording}
            agentDisplayName={undefined}
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
            onAiGenerate={handleAiGenerate}
            isGeneratingAi={isGeneratingAi}
            history={history}
            t={t}
            tCommon={tCommon}
          />
        );
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg" data-testid="agent-config-edit-dialog">
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
                isEvaluating={isEvaluating}
                accuracyLevel={accuracyLevel}
                isNoiseHigh={isNoiseHigh}
                isNoiseCritical={isNoiseCritical}
                staleCoreSkillCount={staleCoreSkills.length}
                isSmartPruning={isSmartPruning}
                onSmartPrune={handleSmartPrune}
              />
            )}
            {renderContent()}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {tCommon('cancel')}
            </Button>
            <Button onClick={handleSave}>{tCommon('confirm')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={settingsSheetOpen} onOpenChange={setSettingsSheetOpen}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-2xl lg:max-w-4xl p-0 overflow-y-auto"
          data-testid="agent-config-edit-dialog"
        >
          <SheetHeader className="sticky top-0 z-10 bg-background border-b border-border px-6 py-4">
            <div className="flex items-center justify-between">
              <SheetTitle>
                {settingsSheetType === 'skills' ? t('skillsSection') : settingsSheetType === 'mcp' ? t('mcpSection') : ''}
              </SheetTitle>
              <Button variant="ghost" size="icon" onClick={() => { setSettingsSheetOpen(false); setSettingsSheetType(null); }} className="h-8 w-8">
                <X size={18} />
              </Button>
            </div>
          </SheetHeader>
          <div className="p-6">
            {settingsSheetType === 'skills' ? <SkillsSection /> : settingsSheetType === 'mcp' ? <MCPSection /> : null}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
};

export default AgentConfigEditDialog;
