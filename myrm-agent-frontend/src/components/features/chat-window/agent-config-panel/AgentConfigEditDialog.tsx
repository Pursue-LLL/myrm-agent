'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { Button } from '@/components/primitives/button';
import { Label } from '@/components/primitives/label';
import { Skill } from '@/store/skill/types';
import { MCPServiceConfig } from '@/store/config/types';
import { BUILTIN_TOOL_IDS, type BuiltinToolId } from '@/store/chat/types';
import { cn } from '@/lib/utils/classnameUtils';
import { type AgentThemeColor, AGENT_COLOR_CLASSES } from '@/components/features/message-box/progress-steps/toolIcons';
import SubagentEntitlementGate from '@/components/billing/SubagentEntitlementGate';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import {
  Wand2,
  Plug,
  FileText,
  Wrench,
  Globe,
  Cable,
  Monitor,
  Image,
  Video,
  Search,
  X,
  Eye,
  Loader2,
  Plus,
  Trash2,
  AlertCircle,
  FolderOpen,
  TerminalSquare,
  BrainCircuit,
  BookMarked,
  KanbanSquare,
  Layers,
  Volume2,
  Bot,
  Link2,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { getApiUrl, apiRequest } from '@/lib/api';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { toast } from '@/hooks/useToast';
import { useAgentNameMap } from '@/hooks/useAgentName';
import type { ConfigCardType } from './AgentConfigCards';
import { ActionSpaceAccuracyRadar } from './ActionSpaceAccuracyRadar';
import { AddMoreButton, SelectableCard } from './AgentConfigSelectableCard';
import dynamic from 'next/dynamic';

type SubagentControlScope = 'leaf' | 'orchestrator';

type EphemeralSubagentConfig = {
  display_name?: string;
  theme_color?: AgentThemeColor;
  control_scope?: SubagentControlScope;
};

const EMPTY_AUTO_RESTORE_DOMAINS: string[] = [];

interface CuPermissionsResponse {
  accessibility: boolean;
  screen_recording: boolean;
  all_granted: boolean;
  platform: string;
  settings_deeplinks: Record<string, string>;
}

function openPermissionDeepLink(url: string) {
  import('@tauri-apps/plugin-shell')
    .then((mod) => mod.open(url))
    .catch(() => {
      window.open(
        'https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac',
        '_blank',
      );
    });
}

const CuPermissionInline = ({ tPanel }: { tPanel: ReturnType<typeof useTranslations> }) => {
  const [status, setStatus] = useState<CuPermissionsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const check = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const data = await apiRequest<CuPermissionsResponse>('/webui/desktop/permissions', { silent: true });
      setStatus(data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  if (error) return null;

  const allOk = status?.all_granted;

  return (
    <div
      className={cn(
        'p-3 rounded-xl border text-xs space-y-1.5',
        allOk
          ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-700 dark:text-emerald-400'
          : 'bg-amber-500/5 border-amber-500/20 text-amber-700 dark:text-amber-400',
      )}
    >
      {loading ? (
        <div className="flex items-center gap-2">
          <Loader2 size={14} className="animate-spin" />
          <span>{tPanel('cuPermission.checking')}</span>
        </div>
      ) : allOk ? (
        <div className="flex items-center gap-2">
          <CheckCircle2 size={14} />
          <span>{tPanel('cuPermission.allGranted')}</span>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle size={14} />
            <span>{tPanel('cuPermission.missing')}</span>
          </div>
          <ul className="ml-5 list-disc space-y-0.5">
            {status && !status.accessibility && <li>{tPanel('cuPermission.accessibilityMissing')}</li>}
            {status && !status.screen_recording && <li>{tPanel('cuPermission.screenRecordingMissing')}</li>}
          </ul>
          <p className="text-[10px] opacity-75">{tPanel('cuPermission.hint')}</p>
          <div className="flex items-center gap-2 pt-1">
            {status?.settings_deeplinks && Object.keys(status.settings_deeplinks).length > 0 && (
              <button
                type="button"
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/15 hover:bg-amber-500/25 font-medium transition-colors"
                onClick={() => {
                  const link = status.settings_deeplinks.accessibility || status.settings_deeplinks.screen_recording;
                  if (link) openPermissionDeepLink(link);
                }}
              >
                <ExternalLink size={12} />
                {tPanel('cuPermission.openSettings')}
              </button>
            )}
            <button
              type="button"
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/15 hover:bg-amber-500/25 font-medium transition-colors"
              onClick={check}
              disabled={loading}
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              {tPanel('cuPermission.recheckBtn')}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

const SmartPromptEditor = dynamic(() => import('./SmartPromptEditor').then((mod) => mod.SmartPromptEditor), {
  ssr: false,
  loading: () => (
    <div className="w-full h-[300px] flex items-center justify-center bg-secondary border rounded-lg text-sm text-muted-foreground">
      <Loader2 size={18} className="animate-spin" />
    </div>
  ),
});

const MCPToolSelector = dynamic(() => import('./MCPToolSelector'), { ssr: false });

const SkillsSection = dynamic(() => import('@/components/features/settings/sections/ai-tools/SkillsSection'), {
  ssr: false,
});
const MCPSection = dynamic(() => import('@/components/features/settings/sections/ai-tools/MCPSection'), {
  ssr: false,
});

interface AgentConfigEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  type: ConfigCardType;
  agentId?: string; // Added for history fetching
  // 可选项
  enabledSkills: Skill[];
  enabledMcps: MCPServiceConfig[];
  // 当前选择
  selectedSkillIds: string[];
  mountedSkillIds?: string[];
  skillConfigs?: Record<string, { is_core?: boolean }>;
  selectedMcpNames: string[];
  mcpToolSelections?: Record<string, string[]>;
  systemPrompt: string;
  useGlobalInstruction: boolean;
  autoRestoreDomains?: string[];
  enabledBuiltinTools: BuiltinToolId[];
  browserEngine?: string;
  browserSource?: string;
  dialogPolicy?: string;
  sessionRecording?: string;
  ephemeralSubagents?: Record<string, unknown>;
  // System Prompt控制
  isSystemPromptHidden?: boolean;
  loadingSystemPrompt?: boolean;
  onShowSystemPrompt?: () => void;
  // 回调
  onSave: (data: {
    selectedSkillIds?: string[];
    mountedSkillIds?: string[];
    skillConfigs?: Record<string, { is_core?: boolean }>;
    selectedMcpNames?: string[];
    mcpToolSelections?: Record<string, string[]>;
    systemPrompt?: string;
    useGlobalInstruction?: boolean;
    enabledBuiltinTools?: BuiltinToolId[];
    browserEngine?: string;
    browserSource?: string;
    dialogPolicy?: string;
    sessionRecording?: string;
    autoRestoreDomains?: string[];
    ephemeralSubagents?: Record<string, unknown>;
    personalityStyle?: string;
  }) => void;
}

/**
 * 智能体配置编辑弹窗
 * 根据传入的 type 显示不同的编辑内容
 */
const AgentConfigEditDialog = ({
  open,
  onOpenChange,
  type,
  agentId,
  enabledSkills,
  enabledMcps,
  selectedSkillIds: initialSkillIds,
  mountedSkillIds: initialMountedSkillIds,
  skillConfigs: initialSkillConfigs = {},
  selectedMcpNames: initialMcpNames,
  mcpToolSelections: initialMcpToolSelections,
  systemPrompt: initialPrompt,
  useGlobalInstruction: initialUseGlobalInstruction,
  autoRestoreDomains: initialAutoRestoreDomains = EMPTY_AUTO_RESTORE_DOMAINS,
  enabledBuiltinTools: initialBuiltinTools,
  browserEngine: initialBrowserEngine,
  browserSource: initialBrowserSource,
  dialogPolicy: initialDialogPolicy,
  sessionRecording: initialSessionRecording,
  ephemeralSubagents: initialEphemeralSubagents = {},
  isSystemPromptHidden = false,
  loadingSystemPrompt = false,
  onShowSystemPrompt,
  onSave,
}: AgentConfigEditDialogProps) => {
  const t = useTranslations('agent.configEditor');
  const tAgent = useTranslations('agent');
  const tPanel = useTranslations('agent.configPanel');
  const tCommon = useTranslations('common');

  // 本地状态
  const [localSkillIds, setLocalSkillIds] = useState<string[]>(initialSkillIds || []);
  const [localMountedSkillIds, setLocalMountedSkillIds] = useState<string[]>(initialMountedSkillIds || []);
  const [localSkillConfigs, setLocalSkillConfigs] = useState<Record<string, { is_core?: boolean }>>(
    initialSkillConfigs || {},
  );
  const [localMcpNames, setLocalMcpNames] = useState<string[]>(initialMcpNames || []);
  const [localMcpToolSelections, setLocalMcpToolSelections] = useState<Record<string, string[]>>(
    initialMcpToolSelections || {},
  );
  const [localPrompt, setLocalPrompt] = useState(initialPrompt || '');
  const [localUseGlobalInstruction, setLocalUseGlobalInstruction] = useState(initialUseGlobalInstruction ?? true);
  const [localAutoRestoreDomains, setLocalAutoRestoreDomains] = useState<string[]>(initialAutoRestoreDomains || []);
  const [localBuiltinTools, setLocalBuiltinTools] = useState<BuiltinToolId[]>(initialBuiltinTools || []);
  const [localBrowserEngine, setLocalBrowserEngine] = useState<string | undefined>(initialBrowserEngine);
  const [localBrowserSource, setLocalBrowserSource] = useState<string | undefined>(initialBrowserSource);
  const [localDialogPolicy, setLocalDialogPolicy] = useState<string | undefined>(initialDialogPolicy);
  const [localSessionRecording, setLocalSessionRecording] = useState<string | undefined>(initialSessionRecording);
  const [localEphemeralSubagents, setLocalEphemeralSubagents] = useState<Record<string, EphemeralSubagentConfig>>(
    initialEphemeralSubagents as Record<string, EphemeralSubagentConfig>,
  );
  const [searchQuery, setSearchQuery] = useState('');

  // 添加 Subagent 相关状态
  const [isAddingSubagent, setIsAddingSubagent] = useState(false);
  const [newSubagentId, setNewSubagentId] = useState('');
  const [newSubagentIdError, setNewSubagentIdError] = useState('');
  const [selectedPreset, setSelectedPreset] = useState<string>('');
  const [subagentToDelete, setSubagentToDelete] = useState<string | null>(null);
  const [displayNameErrors, setDisplayNameErrors] = useState<Record<string, string>>({});

  // 全屏设置面板状态
  const [settingsSheetOpen, setSettingsSheetOpen] = useState(false);
  const [settingsSheetType, setSettingsSheetType] = useState<'skills' | 'mcp' | null>(null);

  // 初始化
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
      setLocalBrowserEngine(initialBrowserEngine);
      setLocalBrowserSource(initialBrowserSource);
      setLocalEphemeralSubagents(initialEphemeralSubagents as Record<string, EphemeralSubagentConfig>);
      setSearchQuery('');
      setIsAddingSubagent(false);
      setNewSubagentId('');
      setNewSubagentIdError('');
      setSelectedPreset('');
      setSubagentToDelete(null);
      setDisplayNameErrors({});
    }
  }, [
    open,
    initialSkillIds,
    initialMountedSkillIds,
    initialSkillConfigs,
    initialMcpNames,
    initialPrompt,
    initialUseGlobalInstruction,
    initialAutoRestoreDomains,
    initialBuiltinTools,
    initialEphemeralSubagents,
  ]);

  // 验证 Subagent ID
  const validateSubagentId = (id: string): string => {
    if (!id) return t('errorIdRequired');
    if (id.length < 2) return t('errorIdTooShort');
    if (id.length > 50) return t('errorIdTooLong');
    if (!/^[a-z0-9_-]+$/.test(id)) return t('errorIdInvalid');
    if (localEphemeralSubagents[id]) return t('errorIdDuplicate');
    return '';
  };

  // 验证 Display Name
  const validateDisplayName = (name: string): string => {
    if (name.length > 100) return t('errorDisplayNameTooLong');
    return '';
  };

  // 预设配置
  const SUBAGENT_PRESETS: Record<
    string,
    EphemeralSubagentConfig & { display_name: string; theme_color: AgentThemeColor }
  > = {
    researcher: { display_name: t('presetResearcher'), theme_color: 'blue', control_scope: 'leaf' },
    coder: { display_name: t('presetCoder'), theme_color: 'green', control_scope: 'leaf' },
    reviewer: { display_name: t('presetReviewer'), theme_color: 'purple', control_scope: 'leaf' },
    analyst: { display_name: t('presetAnalyst'), theme_color: 'orange', control_scope: 'leaf' },
  };

  // 添加 Subagent
  const handleAddSubagent = () => {
    let idToAdd = newSubagentId;
    if (selectedPreset && selectedPreset !== 'custom') {
      idToAdd = selectedPreset;
    }

    const error = validateSubagentId(idToAdd);
    if (error) {
      setNewSubagentIdError(error);
      return;
    }

    const preset = SUBAGENT_PRESETS[idToAdd];
    const newConfig: EphemeralSubagentConfig = preset
      ? { display_name: preset.display_name, theme_color: preset.theme_color, control_scope: preset.control_scope }
      : { display_name: '', theme_color: 'blue', control_scope: 'leaf' };

    setLocalEphemeralSubagents((prev) => ({
      ...prev,
      [idToAdd]: newConfig,
    }));

    setIsAddingSubagent(false);
    setNewSubagentId('');
    setNewSubagentIdError('');
    setSelectedPreset('');
  };

  // 删除 Subagent
  const handleDeleteSubagent = (key: string) => {
    setLocalEphemeralSubagents((prev) => {
      const newSubagents = { ...prev };
      delete newSubagents[key];
      return newSubagents;
    });
    setSubagentToDelete(null);
  };

  const [isGeneratingAi, setIsGeneratingAi] = useState(false);
  const [history, setHistory] = useState<
    Array<{ id: string; version: number; systemPrompt: string; createdAt: string }>
  >([]);

  // Fetch history when dialog opens for instruction
  useEffect(() => {
    if (open && type === 'instruction' && agentId) {
      fetch(getApiUrl(`/user-agents/${agentId}/history`))
        .then((res) => res.json())
        .then((data) => {
          if (data.data) {
            setHistory(data.data);
          }
        })
        .catch((err) => console.error('Failed to fetch history:', err));
    }
  }, [open, type, agentId]);

  const handleAiGenerate = useCallback(
    async (intent: string) => {
      if (!intent.trim()) return;
      setIsGeneratingAi(true);

      // We do NOT clear the existing prompt. We pass it to the backend for context.
      const currentPrompt = localPrompt;

      try {
        const response = await fetch(getApiUrl('/user-agents/generate-prompt'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            intent,
            locale: navigator.language || 'en-US',
            current_prompt: currentPrompt,
          }),
        });

        if (!response.ok) {
          if (response.status === 422) {
            const errorData = await response.json();
            toast({
              title: t('aiGenerateConfigMissing'),
              description: typeof errorData.detail === 'string' ? errorData.detail : undefined,
              variant: 'destructive',
            });
            return;
          }
          throw new Error('Failed to generate prompt');
        }
        if (!response.body) throw new Error('No response body');

        // If we are appending/replacing, we should clear the local prompt ONLY when the first valid chunk arrives
        // to avoid wiping the prompt if the request fails.
        // Even better, since the AI is rewriting the prompt based on context, we replace the whole prompt.
        let isFirstChunk = true;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Parse SSE lines
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || ''; // Keep the last incomplete chunk in buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'content' && data.data) {
                  if (isFirstChunk) {
                    setLocalPrompt(''); // Clear only when we start receiving the new prompt
                    isFirstChunk = false;
                  }
                  setLocalPrompt((prev) => prev + data.data);
                } else if (data.type === 'error') {
                  console.error('AI Generation Error:', data.error);
                  toast({
                    title: t('aiGenerateFailed'),
                    description: typeof data.error === 'string' ? data.error : undefined,
                    variant: 'destructive',
                  });
                }
              } catch (e) {
                console.error('Failed to parse SSE chunk', e);
              }
            }
          }
        }
      } catch (error) {
        console.error('Failed to generate AI prompt:', error);
      } finally {
        setIsGeneratingAi(false);
      }
    },
    [localPrompt, t],
  );

  const handleSave = useCallback(() => {
    // 验证 subagents 的 display_name
    if (type === 'subagents') {
      const hasErrors = Object.values(displayNameErrors).some((error) => error !== '');
      if (hasErrors) {
        return;
      }
    }

    switch (type) {
      case 'skills':
        onSave({
          selectedSkillIds: localSkillIds,
          mountedSkillIds: localMountedSkillIds,
          skillConfigs: localSkillConfigs,
        });
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
          browserEngine: localBrowserEngine,
          browserSource: localBrowserSource,
          dialogPolicy: localDialogPolicy,
          sessionRecording: localSessionRecording,
        });
        break;
      case 'subagents':
        onSave({ ephemeralSubagents: localEphemeralSubagents });
        break;
    }
    onOpenChange(false);
  }, [
    type,
    localSkillIds,
    localSkillConfigs,
    localMcpNames,
    localPrompt,
    localUseGlobalInstruction,
    localBuiltinTools,
    localEphemeralSubagents,
    displayNameErrors,
    onSave,
    onOpenChange,
  ]);

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

  const config = getDialogConfig();

  // 过滤搜索
  const filteredSkills = (enabledSkills || []).filter((s) => s.name.toLowerCase().includes(searchQuery.toLowerCase()));
  const filteredMcps = (enabledMcps || []).filter((m) => m.name.toLowerCase().includes(searchQuery.toLowerCase()));

  // 动作空间复杂度与准确度计算 (真实调用后端 ActionSpaceProfiler)
  const [accuracyData, setAccuracyData] = useState<{
    accuracyLevel: number;
    actionSpaceScore: number;
    maxSafeScore: number;
    isNoiseHigh: boolean;
    isNoiseCritical: boolean;
  }>({
    accuracyLevel: 100,
    actionSpaceScore: 0,
    maxSafeScore: 1500,
    isNoiseHigh: false,
    isNoiseCritical: false,
  });
  const [isEvaluating, setIsEvaluating] = useState(false);

  useEffect(() => {
    setIsEvaluating(true);
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(getApiUrl('/user-agents/evaluate-action-space'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            skill_ids: localSkillIds,
            skill_configs: localSkillConfigs,
            mcp_servers: localMcpNames,
            enabled_builtin_tools: localBuiltinTools,
          }),
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
      } catch (e) {
        console.error('Failed to evaluate action space', e);
      } finally {
        setIsEvaluating(false);
      }
    }, 500); // 500ms debounce
    return () => clearTimeout(timer);
  }, [localSkillIds, localSkillConfigs, localMcpNames, localBuiltinTools]);

  const { accuracyLevel, actionSpaceScore, maxSafeScore, isNoiseHigh, isNoiseCritical } = accuracyData;
  const coreSkillsTokenCost = actionSpaceScore;
  const MAX_CORE_TOKENS = maxSafeScore;
  const noiseLevel = Math.min(100, Math.round((coreSkillsTokenCost / MAX_CORE_TOKENS) * 100));

  // 智能减负 (Smart Pruning)
  const staleCoreSkills = useMemo(() => {
    return localSkillIds.filter((id) => {
      const isCore = localSkillConfigs?.[id]?.is_core ?? true;
      if (!isCore) return false;
      const skill = enabledSkills?.find((s) => s.id === id);
      return skill?.usage_stats?.lifecycle_status === 'stale';
    });
  }, [localSkillIds, localSkillConfigs, enabledSkills]);

  const handleSmartPrune = () => {
    setLocalSkillConfigs((configs) => {
      const newConfigs = { ...configs };
      staleCoreSkills.forEach((id) => {
        newConfigs[id] = { ...newConfigs[id], is_core: false };
      });
      return newConfigs;
    });
  };

  const toggleSkill = (id: string) => {
    setLocalSkillIds((prev) => {
      const isSelected = prev.includes(id);
      if (!isSelected) {
        // 默认新加的技能是 Core
        setLocalSkillConfigs((configs) => ({
          ...configs,
          [id]: { ...configs[id], is_core: true },
        }));
        return [...prev, id];
      }
      return prev.filter((x) => x !== id);
    });
  };

  const toggleMountedSkill = (id: string) => {
    setLocalMountedSkillIds((prev) => {
      const isSelected = prev.includes(id);
      if (!isSelected) {
        return [...prev, id];
      }
      return prev.filter((x) => x !== id);
    });
  };

  // 生成所有关联智能体的字典用于展示溯源徽章
  const mountedOwnerIds = useMemo(() => {
    return (enabledSkills || [])
      .filter((s) => (localMountedSkillIds || []).includes(s.id) && s.scope_agent_id)
      .map((s) => s.scope_agent_id as string);
  }, [enabledSkills, localMountedSkillIds]);
  const agentNameMap = useAgentNameMap(mountedOwnerIds || []);

  const toggleSkillCore = (id: string) => {
    setLocalSkillConfigs((configs) => {
      const currentIsCore = configs[id]?.is_core ?? true;
      return {
        ...configs,
        [id]: { ...configs[id], is_core: !currentIsCore },
      };
    });
  };

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

  const isOwnSkill = useCallback(
    (skill: Skill) => !skill.scope_agent_id || skill.scope_agent_id === agentId,
    [agentId],
  );
  const isOtherSkill = useCallback(
    (skill: Skill) => !!(skill.scope_agent_id && skill.scope_agent_id !== agentId),
    [agentId],
  );

  const renderContent = () => {
    switch (type) {
      case 'skills':
        return (
          <div className="space-y-4">
            {enabledSkills.length > 0 && (
              <>
                {/* 搜索框 */}
                <div className="relative">
                  <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={t('searchPlaceholder')}
                    className="pl-10 h-10 bg-muted/40 border-0 rounded-xl placeholder:text-muted-foreground/50 focus:bg-muted/60 transition-colors"
                  />
                </div>

                {/* 噪音水位表 (Noise Gauge) */}
                <div className="p-3 rounded-xl bg-muted/30 border border-border/50 space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-foreground flex items-center gap-1.5">
                      <Wand2 size={14} className="text-blue-500" />
                      认知负载 (核心技能 Token)
                    </span>
                    <span
                      className={cn(
                        'font-mono text-xs',
                        isNoiseCritical
                          ? 'text-red-500 font-bold'
                          : isNoiseHigh
                            ? 'text-amber-500 font-bold'
                            : 'text-muted-foreground',
                      )}
                    >
                      ~{coreSkillsTokenCost} / {MAX_CORE_TOKENS}
                    </span>
                  </div>
                  <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
                    <div
                      className={cn(
                        'h-full transition-all duration-300',
                        isNoiseCritical ? 'bg-red-500' : isNoiseHigh ? 'bg-amber-500' : 'bg-green-500',
                      )}
                      style={{ width: `${noiseLevel}%` }}
                    />
                  </div>
                  {isNoiseHigh && (
                    <p className={cn('text-xs mt-1', isNoiseCritical ? 'text-red-500' : 'text-amber-500')}>
                      <span className="text-amber-500 mr-1">
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="inline"
                        >
                          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                          <line x1="12" y1="9" x2="12" y2="13" />
                          <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                      </span>{' '}
                      {isNoiseCritical
                        ? '核心技能过多，将严重干扰模型注意力，请精简！'
                        : '认知负载较高，建议将部分技能设为外围技能。'}
                    </p>
                  )}
                  {staleCoreSkills.length > 0 && (
                    <div className="mt-2 p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-start gap-2">
                      <span className="text-blue-500 mt-0.5">
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <circle cx="12" cy="12" r="10" />
                          <path d="M12 16v-4" />
                          <path d="M12 8h.01" />
                        </svg>
                      </span>
                      <div className="flex-1">
                        <p className="text-xs text-blue-700 dark:text-blue-300">
                          发现 {staleCoreSkills.length} 个闲置核心技能（30天未调用）。
                        </p>
                        <button
                          onClick={handleSmartPrune}
                          className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline mt-1"
                        >
                          一键降级为外围技能，释放认知负载
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* 列表 - 物理分区布局 */}
                <div className="space-y-6 max-h-[400px] overflow-y-auto pr-1">
                  {/* 🧠 核心常驻区 (Core) */}
                  {filteredSkills.filter(
                    (s) => isOwnSkill(s) && localSkillIds.includes(s.id) && (localSkillConfigs[s.id]?.is_core ?? true),
                  ).length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between px-1 mb-2">
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                          <svg
                            width="15"
                            height="15"
                            viewBox="0 0 15 15"
                            fill="none"
                            xmlns="http://www.w3.org/2000/svg"
                            className="w-3.5 h-3.5 opacity-70"
                          >
                            <path
                              d="M7.49991 0.876892C7.75836 0.876892 7.96783 1.08636 7.96783 1.34481C7.96783 4.41753 10.5824 6.82029 13.6551 6.82029C13.9136 6.82029 14.123 7.02976 14.123 7.28821C14.123 7.54666 13.9136 7.75613 13.6551 7.75613C10.5824 7.75613 7.96783 10.1589 7.96783 13.2316C7.96783 13.4901 7.75836 13.6995 7.49991 13.6995C7.24146 13.6995 7.03199 13.4901 7.03199 13.2316C7.03199 10.1589 4.41743 7.75613 1.34471 7.75613C1.08626 7.75613 0.876793 7.54666 0.876793 7.28821C0.876793 7.02976 1.08626 6.82029 1.34471 6.82029C4.41743 6.82029 7.03199 4.41753 7.03199 1.34481C7.03199 1.08636 7.24146 0.876892 7.49991 0.876892ZM7.49991 2.92348C7.54134 4.88722 8.65345 6.55938 10.2818 7.28821C8.65345 8.01704 7.54134 9.6892 7.49991 11.6529C7.45848 9.6892 6.34637 8.01704 4.71804 7.28821C6.34637 6.55938 7.45848 4.88722 7.49991 2.92348Z"
                              fill="currentColor"
                              fillRule="evenodd"
                              clipRule="evenodd"
                            />
                          </svg>{' '}
                          核心常驻区 (Core)
                        </h4>
                        <span className="text-[10px] text-muted-foreground">完整注入，极速响应</span>
                      </div>
                      {filteredSkills
                        .filter(
                          (s) =>
                            isOwnSkill(s) && localSkillIds.includes(s.id) && (localSkillConfigs[s.id]?.is_core ?? true),
                        )
                        .map((skill) => {
                          const isSelected = true;
                          const isCore = true;
                          return (
                            <SelectableCard
                              key={skill.id}
                              id={`skill-${skill.id}`}
                              label={skill.name}
                              description={skill.description}
                              checked={isSelected}
                              onCheckedChange={() => toggleSkill(skill.id)}
                              icon={<Wand2 size={14} />}
                              colorClass="text-blue-500"
                              rightElement={
                                <div
                                  className="flex items-center gap-2 px-2 py-1 bg-background/50 rounded-lg border border-border/50 no-card-click"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleSkillCore(skill.id);
                                  }}
                                >
                                  <span className="text-[10px] font-medium text-blue-500">核心 (Core)</span>
                                  <Switch
                                    checked={isCore}
                                    onCheckedChange={() => toggleSkillCore(skill.id)}
                                    className="scale-75 data-[state=checked]:bg-blue-500"
                                  />
                                </div>
                              }
                            />
                          );
                        })}
                    </div>
                  )}

                  {/* 🧰 外围工具箱 (Peripheral) */}
                  {filteredSkills.filter(
                    (s) => isOwnSkill(s) && localSkillIds.includes(s.id) && !(localSkillConfigs[s.id]?.is_core ?? true),
                  ).length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between px-1 mb-2">
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                          <span>🧰</span> 外围工具箱 (Peripheral)
                        </h4>
                        <span className="text-[10px] text-muted-foreground">按需加载，极低负担</span>
                      </div>
                      {filteredSkills
                        .filter(
                          (s) =>
                            isOwnSkill(s) &&
                            localSkillIds.includes(s.id) &&
                            !(localSkillConfigs[s.id]?.is_core ?? true),
                        )
                        .map((skill) => {
                          const isSelected = true;
                          const isCore = false;
                          return (
                            <SelectableCard
                              key={skill.id}
                              id={`skill-${skill.id}`}
                              label={skill.name}
                              description={skill.description}
                              checked={isSelected}
                              onCheckedChange={() => toggleSkill(skill.id)}
                              icon={<Wand2 size={14} />}
                              colorClass="text-blue-500"
                              rightElement={
                                <div
                                  className="flex items-center gap-2 px-2 py-1 bg-background/50 rounded-lg border border-border/50 no-card-click"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleSkillCore(skill.id);
                                  }}
                                >
                                  <span className="text-[10px] font-medium text-muted-foreground">
                                    外围 (Peripheral)
                                  </span>
                                  <Switch
                                    checked={isCore}
                                    onCheckedChange={() => toggleSkillCore(skill.id)}
                                    className="scale-75 data-[state=checked]:bg-blue-500"
                                  />
                                </div>
                              }
                            />
                          );
                        })}
                    </div>
                  )}

                  {/* 🔗 挂载技能 (Mounted) */}
                  {filteredSkills.filter((s) => isOtherSkill(s) && localMountedSkillIds.includes(s.id)).length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between px-1 mb-2">
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                          <Link2 className="w-3.5 h-3.5" /> 挂载技能 (Mounted)
                        </h4>
                        <span className="text-[10px] text-muted-foreground">来自其他智能体的跨域共享能力</span>
                      </div>
                      {filteredSkills
                        .filter((s) => isOtherSkill(s) && localMountedSkillIds.includes(s.id))
                        .map((skill) => {
                          const isSelected = true;
                          const ownerName = skill.scope_agent_id ? agentNameMap.get(skill.scope_agent_id) : undefined;
                          return (
                            <SelectableCard
                              key={skill.id}
                              id={`skill-mounted-${skill.id}`}
                              label={skill.name}
                              description={skill.description}
                              checked={isSelected}
                              onCheckedChange={() => toggleMountedSkill(skill.id)}
                              icon={<Layers size={14} />}
                              colorClass="text-purple-500"
                              rightElement={
                                <div className="flex items-center gap-2">
                                  {ownerName && (
                                    <div className="px-2 py-1 bg-purple-500/10 rounded-lg border border-purple-500/20 flex items-center gap-1">
                                      <Bot className="w-3 h-3 text-purple-500" />
                                      <span className="text-[10px] font-medium text-purple-600 dark:text-purple-400">
                                        {ownerName}
                                      </span>
                                    </div>
                                  )}
                                  <div className="px-2 py-1 bg-background/50 rounded-lg border border-border/50">
                                    <span className="text-[10px] font-medium text-purple-500">挂载中</span>
                                  </div>
                                </div>
                              }
                            />
                          );
                        })}
                    </div>
                  )}

                  {/* ➕ 可选技能 (Available) */}
                  {filteredSkills.filter((s) =>
                    isOwnSkill(s) ? !localSkillIds.includes(s.id) : !localMountedSkillIds.includes(s.id),
                  ).length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between px-1 mb-2">
                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                          <Plus className="w-3.5 h-3.5" /> 可选技能
                        </h4>
                      </div>
                      {filteredSkills
                        .filter((s) =>
                          isOwnSkill(s) ? !localSkillIds.includes(s.id) : !localMountedSkillIds.includes(s.id),
                        )
                        .map((skill) => {
                          const isSelected = false;
                          const isMountable = isOtherSkill(skill);
                          const ownerName =
                            isMountable && skill.scope_agent_id ? agentNameMap.get(skill.scope_agent_id) : undefined;
                          return (
                            <SelectableCard
                              key={skill.id}
                              id={`skill-${skill.id}`}
                              label={skill.name}
                              description={skill.description}
                              checked={isSelected}
                              onCheckedChange={() =>
                                isMountable ? toggleMountedSkill(skill.id) : toggleSkill(skill.id)
                              }
                              icon={isMountable ? <Layers size={14} /> : <Wand2 size={14} />}
                              colorClass={isMountable ? 'text-purple-500' : 'text-blue-500'}
                              rightElement={
                                isMountable ? (
                                  <div className="flex items-center gap-2">
                                    {ownerName && (
                                      <div className="px-2 py-1 bg-purple-500/10 rounded-lg border border-purple-500/20 flex items-center gap-1">
                                        <Bot className="w-3 h-3 text-purple-500" />
                                        <span className="text-[10px] font-medium text-purple-600 dark:text-purple-400">
                                          {ownerName}
                                        </span>
                                      </div>
                                    )}
                                    <div className="px-2 py-1 bg-muted/50 rounded-lg border border-border/50">
                                      <span className="text-[10px] font-medium text-muted-foreground">可挂载</span>
                                    </div>
                                  </div>
                                ) : undefined
                              }
                            />
                          );
                        })}
                    </div>
                  )}
                </div>
              </>
            )}
            {enabledSkills.length === 0 && (
              <div className="py-6 text-center">
                <p className="text-sm text-muted-foreground mb-3">{t('noEnabledSkills')}</p>
              </div>
            )}
            {/* 添加更多按钮 */}
            <AddMoreButton label={t('addMore')} onClick={() => handleOpenSettingsSheet('skills')} />
          </div>
        );

      case 'mcp':
        return (
          <div className="space-y-4">
            {enabledMcps.length > 0 && (
              <>
                <div className="relative">
                  <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
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
            {/* 添加更多按钮 */}
            <AddMoreButton label={t('addMore')} onClick={() => handleOpenSettingsSheet('mcp')} />
          </div>
        );

      case 'builtin_tools': {
        const BUILTIN_TOOL_ICONS: Record<BuiltinToolId, React.ReactNode> = {
          web_search: <Globe size={14} />,
          memory: <BrainCircuit size={14} />,
          file_ops: <FolderOpen size={14} />,
          code_execute: <TerminalSquare size={14} />,
          wiki: <BookMarked size={14} />,
          browser: <Monitor size={14} />,
          computer_use: <Monitor size={14} />,
          image_generation: <Image size={14} />,
          video_generation: <Video size={14} />,
          tts: <Volume2 size={14} />,
          kanban: <KanbanSquare size={14} />,
          llm_map: <Layers size={14} />,
        };
        const toggleBuiltinTool = (id: BuiltinToolId) => {
          setLocalBuiltinTools((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
        };
        return (
          <div className="space-y-4">
            <div className="space-y-2">
              {BUILTIN_TOOL_IDS.map((id) => (
                <SelectableCard
                  key={id}
                  id={`builtin-${id}`}
                  label={tPanel(`builtinToolNames.${id}`)}
                  description={tPanel(`builtinToolDescs.${id}`)}
                  checked={localBuiltinTools.includes(id)}
                  onCheckedChange={() => toggleBuiltinTool(id)}
                  icon={BUILTIN_TOOL_ICONS[id]}
                  colorClass="text-orange-500"
                />
              ))}
            </div>

            {localBuiltinTools.includes('browser') && (
              <div className="space-y-4 p-3 rounded-xl bg-muted/30 border border-border/50">
                <div className="space-y-2">
                  <Label className="text-sm font-medium flex items-center gap-2">
                    <Monitor size={14} className="text-blue-500" />
                    {tPanel('autoRestoreDomains')}
                  </Label>
                  <p className="text-xs text-muted-foreground">{tPanel('autoRestoreDomainsDesc')}</p>
                  <Input
                    value={localAutoRestoreDomains.join(', ')}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (!val.trim()) {
                        setLocalAutoRestoreDomains([]);
                      } else {
                        setLocalAutoRestoreDomains(
                          val
                            .split(',')
                            .map((s) => s.trim())
                            .filter(Boolean),
                        );
                      }
                    }}
                    placeholder="github.com, twitter.com"
                    className="bg-background"
                  />
                </div>

                <div className="space-y-2 pt-2 border-t border-border/50">
                  <Label className="text-sm font-medium flex items-center gap-2">
                    <Globe size={14} className="text-blue-500" />
                    {tAgent('browserEngine.label')}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {tAgent('browserEngine.description')}
                  </p>
                  <Select
                    value={localBrowserEngine || 'chromium_patchright'}
                    onValueChange={(value) =>
                      setLocalBrowserEngine(value === 'chromium_patchright' ? undefined : value)
                    }
                  >
                    <SelectTrigger className="w-full bg-background">
                      <SelectValue placeholder={tAgent('browserEngine.label')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="chromium_patchright">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{tAgent('browserEngine.chromium')}</span>
                          <span className="text-xs text-muted-foreground">
                            {tAgent('browserEngine.chromiumDesc')}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="firefox_camoufox">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{tAgent('browserEngine.camoufox')}</span>
                          <span className="text-xs text-muted-foreground">
                            {tAgent('browserEngine.camoufoxDesc')}
                          </span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Browser Source (Launch Mode) */}
                <div className="space-y-2 pt-2 border-t border-border/50">
                  <Label className="text-sm font-medium flex items-center gap-2">
                    <Cable size={14} className="text-green-500" />
                    {t('browserSource.label')}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {t('browserSource.description')}
                  </p>
                  <Select
                    value={localBrowserSource || 'auto'}
                    onValueChange={(value) =>
                      setLocalBrowserSource(value === 'auto' ? undefined : value)
                    }
                  >
                    <SelectTrigger className="w-full bg-background">
                      <SelectValue placeholder={t('browserSource.placeholder')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('browserSource.options.auto')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('browserSource.options.autoDesc')}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="extension">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('browserSource.options.extension')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('browserSource.options.extensionDesc')}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="launch">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('browserSource.options.launch')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('browserSource.options.launchDesc')}
                          </span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  {localBrowserSource === 'extension' && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
                      <AlertCircle size={12} />
                      {t('browserSource.extensionWarning')}
                    </p>
                  )}
                </div>

                <div className="space-y-2 pt-2 border-t border-border/50">
                  <Label className="text-sm font-medium flex items-center gap-2">
                    {t('dialogPolicy.label')}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {t('dialogPolicy.description')}
                  </p>
                  <Select
                    value={localDialogPolicy || 'smart'}
                    onValueChange={(value) =>
                      setLocalDialogPolicy(value === 'smart' ? undefined : value)
                    }
                  >
                    <SelectTrigger className="w-full bg-background">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="smart">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('dialogPolicy.options.smart')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('dialogPolicy.options.smartDesc')}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="auto_accept">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('dialogPolicy.options.autoAccept')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('dialogPolicy.options.autoAcceptDesc')}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="auto_dismiss">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('dialogPolicy.options.autoDismiss')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('dialogPolicy.options.autoDismissDesc')}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="wait_for_agent">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('dialogPolicy.options.waitForAgent')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('dialogPolicy.options.waitForAgentDesc')}
                          </span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2 pt-2 border-t border-border/50">
                  <Label className="text-sm font-medium flex items-center gap-2">
                    {t('sessionRecording.label')}
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    {t('sessionRecording.description')}
                  </p>
                  <Select
                    value={localSessionRecording || 'off'}
                    onValueChange={(value) =>
                      setLocalSessionRecording(value === 'off' ? undefined : value)
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="off">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('sessionRecording.options.off')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('sessionRecording.options.offDesc')}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="on_failure">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('sessionRecording.options.onFailure')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('sessionRecording.options.onFailureDesc')}
                          </span>
                        </div>
                      </SelectItem>
                      <SelectItem value="always">
                        <div className="flex flex-col py-1">
                          <span className="font-medium">{t('sessionRecording.options.always')}</span>
                          <span className="text-xs text-muted-foreground">
                            {t('sessionRecording.options.alwaysDesc')}
                          </span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {localBuiltinTools.includes('computer_use') && (
              <CuPermissionInline tPanel={tPanel} />
            )}
          </div>
        );
      }

      case 'subagents': {
        const subagentEntries = Object.entries(localEphemeralSubagents);
        const availableColors: AgentThemeColor[] = [
          'blue',
          'green',
          'purple',
          'orange',
          'pink',
          'cyan',
          'amber',
          'red',
        ];

        const handleSubagentDisplayNameChange = (subagentKey: string, newDisplayName: string) => {
          const error = validateDisplayName(newDisplayName);
          setDisplayNameErrors((prev) => ({
            ...prev,
            [subagentKey]: error,
          }));

          setLocalEphemeralSubagents((prev) => ({
            ...prev,
            [subagentKey]: {
              ...prev[subagentKey],
              display_name: newDisplayName,
            },
          }));
        };

        const handleSubagentThemeColorChange = (subagentKey: string, newColor: AgentThemeColor) => {
          setLocalEphemeralSubagents((prev) => ({
            ...prev,
            [subagentKey]: {
              ...prev[subagentKey],
              theme_color: newColor,
            },
          }));
        };

        const handleSubagentControlScopeChange = (subagentKey: string, newScope: SubagentControlScope) => {
          setLocalEphemeralSubagents((prev) => ({
            ...prev,
            [subagentKey]: {
              ...prev[subagentKey],
              control_scope: newScope,
            },
          }));
        };

        const hasValidationErrors = Object.values(displayNameErrors).some((error) => error !== '');

        return (
          <SubagentEntitlementGate>
            <div className="space-y-4">
              {/* 添加 Subagent 按钮 */}
              <Button
                onClick={() => setIsAddingSubagent(true)}
                variant="outline"
                className="w-full gap-2 border-dashed"
              >
                <Plus size={16} />
                {t('addSubagent')}
              </Button>

              {/* Subagent 列表 */}
              {subagentEntries.length > 0 ? (
                <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
                  {subagentEntries.map(([key, config]: [string, EphemeralSubagentConfig]) => (
                    <div key={key} className="p-4 rounded-lg border border-border/50 bg-muted/30 space-y-3">
                      {/* 标题行：ID + 删除按钮 */}
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm font-medium text-foreground">{key}</div>
                        <Button
                          onClick={() => setSubagentToDelete(key)}
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-destructive hover:text-destructive hover:bg-destructive/10"
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>

                      {/* Display Name 输入框 */}
                      <div className="space-y-1.5">
                        <Label htmlFor={`display-name-${key}`} className="text-xs font-medium text-muted-foreground">
                          {t('subagentDisplayName')}
                        </Label>
                        <Input
                          id={`display-name-${key}`}
                          value={config.display_name || ''}
                          onChange={(e) => handleSubagentDisplayNameChange(key, e.target.value)}
                          placeholder={t('subagentDisplayNamePlaceholder')}
                          className={cn(
                            'h-9 text-sm',
                            displayNameErrors[key] && 'border-destructive focus-visible:ring-destructive',
                          )}
                        />
                        {displayNameErrors[key] && (
                          <div className="flex items-center gap-1.5 text-xs text-destructive">
                            <AlertCircle size={12} />
                            {displayNameErrors[key]}
                          </div>
                        )}
                      </div>

                      <div className="space-y-1.5">
                        <Label htmlFor={`control-scope-${key}`} className="text-xs font-medium text-muted-foreground">
                          {t('subagentRole')}
                        </Label>
                        <Select
                          value={config.control_scope || 'leaf'}
                          onValueChange={(value) =>
                            handleSubagentControlScopeChange(key, value as SubagentControlScope)
                          }
                        >
                          <SelectTrigger id={`control-scope-${key}`} className="h-9 text-sm">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="leaf">
                              <div className="flex flex-col py-1">
                                <span>{t('subagentRoleWorker')}</span>
                                <span className="text-xs text-muted-foreground">{t('subagentRoleWorkerDesc')}</span>
                              </div>
                            </SelectItem>
                            <SelectItem value="orchestrator">
                              <div className="flex flex-col py-1">
                                <span>{t('subagentRoleCoordinator')}</span>
                                <span className="text-xs text-muted-foreground">
                                  {t('subagentRoleCoordinatorDesc')}
                                </span>
                              </div>
                            </SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      {/* Theme Color 选择器 */}
                      <div className="space-y-1.5">
                        <Label htmlFor={`theme-color-${key}`} className="text-xs font-medium text-muted-foreground">
                          {t('subagentThemeColor')}
                        </Label>
                        <Select
                          value={config.theme_color || 'blue'}
                          onValueChange={(value) => handleSubagentThemeColorChange(key, value as AgentThemeColor)}
                        >
                          <SelectTrigger className="h-9 text-sm">
                            <SelectValue>
                              <div className="flex items-center gap-2">
                                <div
                                  className={cn(
                                    'w-4 h-4 rounded-full border-2',
                                    AGENT_COLOR_CLASSES[config.theme_color as AgentThemeColor]?.border ||
                                      AGENT_COLOR_CLASSES.blue.border,
                                  )}
                                  style={{
                                    backgroundColor:
                                      config.theme_color === 'blue'
                                        ? '#3b82f6'
                                        : config.theme_color === 'green'
                                          ? '#10b981'
                                          : config.theme_color === 'purple'
                                            ? '#a855f7'
                                            : config.theme_color === 'orange'
                                              ? '#f97316'
                                              : config.theme_color === 'pink'
                                                ? '#ec4899'
                                                : config.theme_color === 'cyan'
                                                  ? '#06b6d4'
                                                  : config.theme_color === 'amber'
                                                    ? '#f59e0b'
                                                    : config.theme_color === 'red'
                                                      ? '#ef4444'
                                                      : '#3b82f6',
                                  }}
                                />
                                <span className="capitalize">{config.theme_color || 'blue'}</span>
                              </div>
                            </SelectValue>
                          </SelectTrigger>
                          <SelectContent>
                            {availableColors.map((color) => (
                              <SelectItem key={color} value={color}>
                                <div className="flex items-center gap-2">
                                  <div
                                    className={cn('w-4 h-4 rounded-full border-2', AGENT_COLOR_CLASSES[color].border)}
                                    style={{
                                      backgroundColor:
                                        color === 'blue'
                                          ? '#3b82f6'
                                          : color === 'green'
                                            ? '#10b981'
                                            : color === 'purple'
                                              ? '#a855f7'
                                              : color === 'orange'
                                                ? '#f97316'
                                                : color === 'pink'
                                                  ? '#ec4899'
                                                  : color === 'cyan'
                                                    ? '#06b6d4'
                                                    : color === 'amber'
                                                      ? '#f59e0b'
                                                      : color === 'red'
                                                        ? '#ef4444'
                                                        : '#3b82f6',
                                    }}
                                  />
                                  <span className="capitalize">{color}</span>
                                </div>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center">
                  <p className="text-sm text-muted-foreground mb-2">{t('noSubagents')}</p>
                  <p className="text-xs text-muted-foreground/70">{t('noSubagentsDesc')}</p>
                </div>
              )}

              {/* 添加 Subagent 对话框 */}
              <Dialog open={isAddingSubagent} onOpenChange={setIsAddingSubagent}>
                <DialogContent className="max-w-md">
                  <DialogHeader>
                    <DialogTitle>{t('addSubagent')}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    {/* 预设选择 */}
                    <div className="space-y-2">
                      <Label>{t('selectPreset')}</Label>
                      <Select
                        value={selectedPreset}
                        onValueChange={(value) => {
                          setSelectedPreset(value);
                          if (value !== 'custom') {
                            setNewSubagentId(value);
                            setNewSubagentIdError('');
                          } else {
                            setNewSubagentId('');
                          }
                        }}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder={t('selectPreset')} />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.keys(SUBAGENT_PRESETS).map((preset) => (
                            <SelectItem key={preset} value={preset}>
                              {SUBAGENT_PRESETS[preset].display_name}
                            </SelectItem>
                          ))}
                          <SelectItem value="custom">{t('customId')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* 自定义 ID 输入 */}
                    {(selectedPreset === 'custom' || !selectedPreset) && (
                      <div className="space-y-2">
                        <Label htmlFor="new-subagent-id">{t('subagentIdLabel')}</Label>
                        <Input
                          id="new-subagent-id"
                          value={newSubagentId}
                          onChange={(e) => {
                            setNewSubagentId(e.target.value);
                            setNewSubagentIdError('');
                          }}
                          placeholder={t('subagentIdPlaceholder')}
                          className={cn(newSubagentIdError && 'border-destructive focus-visible:ring-destructive')}
                        />
                        {newSubagentIdError && (
                          <div className="flex items-center gap-1.5 text-xs text-destructive">
                            <AlertCircle size={12} />
                            {newSubagentIdError}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setIsAddingSubagent(false)}>
                      {tCommon('cancel')}
                    </Button>
                    <Button onClick={handleAddSubagent}>{tCommon('confirm')}</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              {/* 删除确认对话框 */}
              <Dialog open={!!subagentToDelete} onOpenChange={() => setSubagentToDelete(null)}>
                <DialogContent className="max-w-md">
                  <DialogHeader>
                    <DialogTitle>{t('deleteSubagent')}</DialogTitle>
                  </DialogHeader>
                  <p className="text-sm text-muted-foreground py-4">{t('confirmDeleteSubagent')}</p>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setSubagentToDelete(null)}>
                      {tCommon('cancel')}
                    </Button>
                    <Button
                      variant="destructive"
                      onClick={() => subagentToDelete && handleDeleteSubagent(subagentToDelete)}
                    >
                      {tCommon('confirm')}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              {/* 验证错误提示 */}
              {hasValidationErrors && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30 flex items-start gap-2">
                  <AlertCircle size={16} className="text-destructive mt-0.5 shrink-0" />
                  <p className="text-sm text-destructive">{t('fixValidationErrors')}</p>
                </div>
              )}
            </div>
          </SubagentEntitlementGate>
        );
      }

      case 'instruction':
        return (
          <div className="space-y-4">
            {/* 使用全局指令开关 */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border border-border/50">
              <div className="flex-1 pr-4">
                <h4 className="text-sm font-medium text-foreground">{t('useGlobalInstruction')}</h4>
                <p className="text-xs text-muted-foreground mt-0.5">{t('useGlobalInstructionDesc')}</p>
              </div>
              <Switch checked={localUseGlobalInstruction} onCheckedChange={setLocalUseGlobalInstruction} />
            </div>

            {/* System Prompt隐藏警告和Show按钮 */}
            {isSystemPromptHidden && localPrompt === '⚠️ [Hidden for security]' && (
              <div className="p-4 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <h4 className="text-sm font-medium text-amber-900 dark:text-amber-100">
                      {t('systemPromptHidden')}
                    </h4>
                    <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">{t('systemPromptHiddenDesc')}</p>
                  </div>
                  <Button
                    onClick={onShowSystemPrompt}
                    disabled={loadingSystemPrompt}
                    variant="outline"
                    size="sm"
                    className="ml-4 gap-2"
                  >
                    {loadingSystemPrompt ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        {tCommon('loading')}
                      </>
                    ) : (
                      <>
                        <Eye size={14} />
                        {t('showPrompt')}
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* 智能体指令输入框 */}
            <SmartPromptEditor
              value={localPrompt}
              onChange={setLocalPrompt}
              onAiGenerate={handleAiGenerate}
              isGenerating={isGeneratingAi}
              history={history}
              onRestoreHistory={(h) => setLocalPrompt(h.systemPrompt || '')}
              className="w-full h-[300px]"
            />
          </div>
        );
    }
  };

  // 打开设置面板
  const handleOpenSettingsSheet = useCallback((sheetType: 'skills' | 'mcp') => {
    setSettingsSheetType(sheetType);
    setSettingsSheetOpen(true);
  }, []);

  // 关闭设置面板
  const handleCloseSettingsSheet = useCallback(() => {
    setSettingsSheetOpen(false);
    setSettingsSheetType(null);
  }, []);

  // 渲染设置面板内容
  const renderSettingsSheetContent = () => {
    switch (settingsSheetType) {
      case 'skills':
        return <SkillsSection />;
      case 'mcp':
        return <MCPSection />;
      default:
        return null;
    }
  };

  // 获取设置面板标题
  const getSettingsSheetTitle = () => {
    switch (settingsSheetType) {
      case 'skills':
        return t('skillsSection');
      case 'mcp':
        return t('mcpSection');
      default:
        return '';
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg">
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

      {/* 全屏设置面板 */}
      <Sheet open={settingsSheetOpen} onOpenChange={setSettingsSheetOpen}>
        <SheetContent side="right" className="w-full sm:max-w-2xl lg:max-w-4xl p-0 overflow-y-auto">
          <SheetHeader className="sticky top-0 z-10 bg-background border-b border-border px-6 py-4">
            <div className="flex items-center justify-between">
              <SheetTitle>{getSettingsSheetTitle()}</SheetTitle>
              <Button variant="ghost" size="icon" onClick={handleCloseSettingsSheet} className="h-8 w-8">
                <X size={18} />
              </Button>
            </div>
          </SheetHeader>
          <div className="p-6">{renderSettingsSheetContent()}</div>
        </SheetContent>
      </Sheet>
    </>
  );
};

export default AgentConfigEditDialog;
