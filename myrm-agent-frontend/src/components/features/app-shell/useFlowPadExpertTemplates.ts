/**
 * [INPUT]
 * - getTemplates (POS: 专家模板发现)
 * - instantiateTemplateWithMetrics (POS: 模板召唤与漏斗埋点)
 * - useAgentStore (POS: 召唤后刷新可用 agent 列表)
 *
 * [OUTPUT]
 * - useFlowPadExpertTemplates: 团队模板列表/搜索/召唤状态与动作。
 *
 * [POS]
 * FlowPad Inline 路由菜单里的"专家召唤"数据层：菜单打开时加载团队模板（失败后等用户重试，每个会话再自动试一次），
 * 按搜索词过滤，召唤成功后刷新名单并把路由切到新专家，同时上报召唤漏斗各阶段。
 */
import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import useAgentStore from '@/store/useAgentStore';
import type { FlowPadMode } from '@/store/useFlowPadStore';
import { getTemplates, type TemplateListItem } from '@/services/agentTemplates';
import {
  recordExpertSummonRouteApplied,
  recordExpertSummonRouteApplyFailed,
  recordExpertSummonSearchUsed,
  recordExpertSummonSurfaceViewed,
} from '@/services/expertSummonMetrics';
import {
  normalizeTemplateSearchText,
  resolveTemplateKind,
  templateMatchesSearchQuery,
} from '@/services/templateDiscovery';
import { extractSummonErrorMessage, instantiateTemplateWithMetrics } from '@/services/templateSummon';
import type { SummonAttribution } from './useFlowPadSummonAttribution';

interface UseFlowPadExpertTemplatesOptions {
  mode: FlowPadMode;
  agentRouteMenuOpen: boolean;
  inlineRouteSwitching: boolean;
  isSubmitting: boolean;
  /** Routes the pad to an agent; resolves true once the route is applied. */
  selectRouteAgent: (agentId: string) => Promise<boolean>;
  /** Hides the hint of an earlier failed route switch. */
  dismissRouteSwitchError: () => void;
  beginSummon: (attribution: SummonAttribution) => void;
  /** Receives the starter prompt of a use case chip. */
  setText: Dispatch<SetStateAction<string>>;
}

export function useFlowPadExpertTemplates({
  mode,
  agentRouteMenuOpen,
  inlineRouteSwitching,
  isSubmitting,
  selectRouteAgent,
  dismissRouteSwitchError,
  beginSummon,
  setText,
}: UseFlowPadExpertTemplatesOptions) {
  const t = useTranslations('flowPad');
  const fetchAgents = useAgentStore((state) => state.fetchAgents);

  const [templateSearchQuery, setTemplateSearchQuery] = useState('');
  const [expertTemplates, setExpertTemplates] = useState<TemplateListItem[] | null>(null);
  const [expertTemplatesError, setExpertTemplatesError] = useState(false);
  const [instantiatingTemplateId, setInstantiatingTemplateId] = useState<string | null>(null);
  const hasReportedSurfaceViewRef = useRef(false);
  const hasReportedSearchRef = useRef(false);
  const requestInFlightRef = useRef(false);

  /**
   * Forgets the search, the once-per-session reports and an earlier load failure, so each session tries the list
   * once more; loaded templates stay cached for the next session.
   */
  const resetTemplates = useCallback(() => {
    setTemplateSearchQuery('');
    setInstantiatingTemplateId(null);
    setExpertTemplatesError(false);
    hasReportedSurfaceViewRef.current = false;
    hasReportedSearchRef.current = false;
  }, []);

  const menuShowsTemplates = mode === 'inline' && agentRouteMenuOpen;
  const expertTemplatesLoading = menuShowsTemplates && expertTemplates === null && !expertTemplatesError;

  // Asks while the open menu has nothing to show; a failed request waits for the user's retry instead.
  useEffect(() => {
    if (!expertTemplatesLoading || requestInFlightRef.current) {
      return;
    }
    requestInFlightRef.current = true;
    getTemplates()
      .then((templates) => setExpertTemplates(templates.filter((item) => item.agent_type === 'team')))
      .catch((error: unknown) => {
        console.error('FlowPad template list fetch failed:', error);
        setExpertTemplatesError(true);
      })
      .finally(() => {
        requestInFlightRef.current = false;
      });
  }, [expertTemplatesLoading]);

  const retryExpertTemplates = useCallback(() => setExpertTemplatesError(false), []);

  useEffect(() => {
    if (mode !== 'inline' || !agentRouteMenuOpen || hasReportedSurfaceViewRef.current) {
      return;
    }
    hasReportedSurfaceViewRef.current = true;
    recordExpertSummonSurfaceViewed('flow_pad_inline', 'flowpad:inline');
  }, [mode, agentRouteMenuOpen]);

  useEffect(() => {
    if (mode !== 'inline' || !agentRouteMenuOpen || hasReportedSearchRef.current) {
      return;
    }
    const normalizedQuery = normalizeTemplateSearchText(templateSearchQuery);
    if (!normalizedQuery) {
      return;
    }
    hasReportedSearchRef.current = true;
    recordExpertSummonSearchUsed('flow_pad_inline', normalizedQuery.length, 'flowpad:inline');
  }, [mode, agentRouteMenuOpen, templateSearchQuery]);

  const filteredExpertTemplates = useMemo(() => {
    return (expertTemplates ?? []).filter((template) => templateMatchesSearchQuery(template, templateSearchQuery));
  }, [expertTemplates, templateSearchQuery]);

  const instantiateExpertTemplate = useCallback(
    async (template: TemplateListItem, starterPrompt?: string) => {
      if (instantiatingTemplateId || inlineRouteSwitching || isSubmitting) {
        return;
      }
      const normalizedStarterPrompt = starterPrompt?.trim() ?? '';
      const fromSearch = normalizeTemplateSearchText(templateSearchQuery).length > 0;
      const usedUseCase = normalizedStarterPrompt.length > 0;
      const trigger = usedUseCase ? 'use_case_chip' : 'template_card';
      const templateKind = resolveTemplateKind(template.agent_type);
      const funnel = { contextKey: 'flowpad:inline', templateKind, fromSearch, usedUseCase };
      if (normalizedStarterPrompt) {
        // Preserve existing draft to avoid overriding in-progress user edits.
        setText((prev) => (prev.trim() ? prev : normalizedStarterPrompt));
      }
      setInstantiatingTemplateId(template.id);
      dismissRouteSwitchError();
      try {
        const newAgent = await instantiateTemplateWithMetrics({
          templateId: template.id,
          surface: 'flow_pad_inline',
          trigger,
          templateKind,
          fromSearch,
          usedUseCase,
          contextKey: 'flowpad:inline',
        });
        await fetchAgents(true);
        const routeApplied = await selectRouteAgent(newAgent.id);
        if (routeApplied) {
          recordExpertSummonRouteApplied('flow_pad_inline', trigger, funnel);
          beginSummon({ trigger, templateKind, fromSearch, usedUseCase });
        } else {
          recordExpertSummonRouteApplyFailed('flow_pad_inline', trigger, funnel);
        }
      } catch (error) {
        console.error('FlowPad expert template instantiate failed:', error);
        toast.error(extractSummonErrorMessage(error, t('inlineRouteTemplateApplyFailed')), { duration: 3000 });
      } finally {
        setInstantiatingTemplateId(null);
      }
    },
    [
      instantiatingTemplateId,
      inlineRouteSwitching,
      isSubmitting,
      templateSearchQuery,
      fetchAgents,
      selectRouteAgent,
      dismissRouteSwitchError,
      beginSummon,
      setText,
      t,
    ],
  );

  return {
    templateSearchQuery,
    setTemplateSearchQuery,
    expertTemplatesLoading,
    expertTemplatesError,
    filteredExpertTemplates,
    instantiatingTemplateId,
    retryExpertTemplates,
    instantiateExpertTemplate,
    resetTemplates,
  };
}
