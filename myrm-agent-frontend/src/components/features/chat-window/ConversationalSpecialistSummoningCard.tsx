'use client';

import { useState, useCallback } from 'react';
import {
  Users,
  Sparkles,
  Bot,
  Layers,
  ArrowRight,
  RotateCcw,
  CheckCircle2,
  FileCode,
  Palette,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react';

export type SpecialistDomain =
  | 'copywriting_polish'
  | 'visual_design'
  | 'code_audit'
  | 'market_research'
  | 'data_analysis';

export interface SpecialistProfileData {
  specialist_id: string;
  name: string;
  mention_tag: string;
  domain: SpecialistDomain;
  description: string;
  suggested_keywords: string[];
}

export interface StructuredAggregationCardData {
  card_id: string;
  summon_id: string;
  specialist_id: string;
  specialist_name: string;
  card_type: string;
  headline: string;
  deliverable_payload: string;
  artifacts: string[];
  created_at: number;
}

export interface SummonSessionExecutionData {
  summon_id: string;
  chat_id: string;
  specialist_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  trigger_source: 'explicit_mention' | 'intent_detection';
  instruction: string;
  aggregation_card: StructuredAggregationCardData | null;
  execution_seconds: number;
}

export interface ConversationalSpecialistSummoningCardProps {
  chatId?: string;
  initialExecutions?: SummonSessionExecutionData[];
  onDismiss?: () => void;
}

const DEFAULT_SPECIALISTS: SpecialistProfileData[] = [
  {
    specialist_id: 'specialist_humanize',
    name: '去AI味文案润色专家',
    mention_tag: '@去AI味专家',
    domain: 'copywriting_polish',
    description: '消除大模型机械套话与说教感，转化为自然口语化表达',
    suggested_keywords: ['去ai味', '润色', '更自然', '口语化'],
  },
  {
    specialist_id: 'specialist_visual',
    name: '视觉与配图设计专家',
    mention_tag: '@视觉专家',
    domain: 'visual_design',
    description: '视觉色彩搭配、SVG矢量图生成与多场景配图渲染建议',
    suggested_keywords: ['配图', '视觉设计', '出图', '海报', '封面'],
  },
  {
    specialist_id: 'specialist_code_audit',
    name: '代码与安全审计专家',
    mention_tag: '@代码审计师',
    domain: 'code_audit',
    description: '高危漏洞排查、注入防御、边界条件审计与静态安全审查',
    suggested_keywords: ['代码审计', '安全检查', '漏洞扫描', 'audit'],
  },
  {
    specialist_id: 'specialist_market_research',
    name: '竞品与商业洞察分析师',
    mention_tag: '@竞品分析师',
    domain: 'market_research',
    description: '分析竞品产品矩阵、商业模式差异、功能对标与市场机会',
    suggested_keywords: ['竞品分析', '市场分析', '对标调研', '竞品对比'],
  },
];

export function ConversationalSpecialistSummoningCard({
  chatId = 'default-chat-session',
  initialExecutions = [],
  onDismiss,
}: ConversationalSpecialistSummoningCardProps) {
  const [inputText, setInputText] = useState('');
  const [detectedSpecialist, setDetectedSpecialist] = useState<SpecialistProfileData | null>(null);
  const [triggerMode, setTriggerMode] = useState<'explicit_mention' | 'intent_detection' | null>(null);
  const [executions, setExecutions] = useState<SummonSessionExecutionData[]>(initialExecutions);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInputText(val);

    // 1. Detect explicit @mention
    const matchedMention = DEFAULT_SPECIALISTS.find((s) => val.includes(s.mention_tag));
    if (matchedMention) {
      setDetectedSpecialist(matchedMention);
      setTriggerMode('explicit_mention');
      return;
    }

    // 2. Detect implicit keywords
    const lower = val.toLowerCase();
    const matchedKeyword = DEFAULT_SPECIALISTS.find((s) =>
      s.suggested_keywords.some((kw) => lower.includes(kw.toLowerCase()))
    );
    if (matchedKeyword) {
      setDetectedSpecialist(matchedKeyword);
      setTriggerMode('intent_detection');
      return;
    }

    setDetectedSpecialist(null);
    setTriggerMode(null);
  };

  const handleQuickMention = useCallback((specialist: SpecialistProfileData) => {
    setInputText(`${specialist.mention_tag} 帮我协同处理此阶段任务：优化并输出专业交付物`);
    setDetectedSpecialist(specialist);
    setTriggerMode('explicit_mention');
  }, []);

  const handleDispatchSummon = useCallback(() => {
    if (!detectedSpecialist || !inputText.trim()) {
      return;
    }

    const summonId = `summon-${Date.now()}`;
    const cleanedInstruction = inputText.replace(detectedSpecialist.mention_tag, '').trim() || inputText;

    const aggregationCard: StructuredAggregationCardData = {
      card_id: `card-${summonId}`,
      summon_id: summonId,
      specialist_id: detectedSpecialist.specialist_id,
      specialist_name: detectedSpecialist.name,
      card_type: detectedSpecialist.domain,
      headline: `【${detectedSpecialist.name}】交付成果：${cleanedInstruction.slice(0, 24)}...`,
      deliverable_payload: `已完成专业化沙箱隔离执行。核心产物格式为 ${detectedSpecialist.domain}，无主会话长上下文污染。`,
      artifacts: [`artifact_${summonId}_${detectedSpecialist.domain}.json`],
      created_at: Date.now() / 1000,
    };

    const newExecution: SummonSessionExecutionData = {
      summon_id: summonId,
      chat_id: chatId,
      specialist_id: detectedSpecialist.specialist_id,
      status: 'completed',
      trigger_source: triggerMode || 'explicit_mention',
      instruction: cleanedInstruction,
      aggregation_card: aggregationCard,
      execution_seconds: 0.85,
    };

    setExecutions((prev) => [newExecution, ...prev]);
    setStatusMessage(
      `Specialist '${detectedSpecialist.name}' summoned via ${triggerMode}. Structured card bridged to chat.`
    );
    setInputText('');
    setDetectedSpecialist(null);
    setTriggerMode(null);
  }, [chatId, detectedSpecialist, inputText, triggerMode]);

  const handleReset = useCallback(() => {
    setExecutions([]);
    setInputText('');
    setDetectedSpecialist(null);
    setTriggerMode(null);
    setStatusMessage('Specialist summoning state reset.');
  }, []);

  return (
    <dialog
      open
      className="relative flex flex-col w-full max-w-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-lg p-5 text-zinc-900 dark:text-zinc-100 z-50 overflow-hidden"
      data-testid="specialist-summoning-card"
    >
      <div className="flex items-center justify-between pb-3 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center space-x-2">
          <Bot className="w-5 h-5 text-indigo-500" />
          <h3 className="font-semibold text-base">Conversational Multi-Specialist Summoning</h3>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss dialog"
            className="text-xs px-2.5 py-1 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 transition-colors"
          >
            Dismiss
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 my-4">
        <div className="flex flex-col p-3 rounded-lg bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-700">
          <span className="text-xs text-zinc-500 font-medium">Available Specialists</span>
          <span className="text-xl font-bold mt-1" data-testid="stat-available-specialists">
            {DEFAULT_SPECIALISTS.length}
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-indigo-50/60 dark:bg-indigo-950/30 border border-indigo-200/60 dark:border-indigo-800/50">
          <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">
            Active Summoned
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-summoned-count">
            {executions.length}
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-emerald-50/60 dark:bg-emerald-950/30 border border-emerald-200/60 dark:border-emerald-800/50">
          <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
            Bridged Cards
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-bridged-cards">
            {executions.filter((e) => e.aggregation_card !== null).length}
          </span>
        </div>
      </div>

      <div className="mb-4">
        <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
          Quick @-Mention Specialist Roster
        </div>
        <div className="grid grid-cols-2 gap-2" data-testid="specialist-roster-grid">
          {DEFAULT_SPECIALISTS.map((s) => (
            <button
              key={s.specialist_id}
              onClick={() => handleQuickMention(s)}
              className="flex items-start p-2 rounded-lg border text-left bg-zinc-50 dark:bg-zinc-800/30 border-zinc-200 dark:border-zinc-700/60 hover:border-indigo-400 dark:hover:border-indigo-600 transition-colors"
              data-testid={`btn-quick-mention-${s.specialist_id}`}
            >
              <div className="p-1 rounded bg-indigo-100 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 mr-2 shrink-0">
                {s.domain === 'copywriting_polish' && <Sparkles className="w-3.5 h-3.5" />}
                {s.domain === 'visual_design' && <Palette className="w-3.5 h-3.5" />}
                {s.domain === 'code_audit' && <ShieldAlert className="w-3.5 h-3.5" />}
                {s.domain === 'market_research' && <TrendingUp className="w-3.5 h-3.5" />}
              </div>
              <div className="overflow-hidden">
                <div className="text-xs font-semibold text-zinc-800 dark:text-zinc-200 flex items-center space-x-1">
                  <span>{s.name}</span>
                  <span className="font-mono text-[10px] text-indigo-500">{s.mention_tag}</span>
                </div>
                <div className="text-[11px] text-zinc-400 truncate mt-0.5">{s.description}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2 mb-4">
        <div className="flex items-center space-x-1 text-xs text-zinc-500 font-medium">
          <Layers className="w-3.5 h-3.5" />
          <span>Natural Language Input & Intent Sensing</span>
        </div>
        <div className="flex items-center space-x-2">
          <input
            type="text"
            value={inputText}
            onChange={handleInputChange}
            placeholder="输入 '@去AI味专家' 或描述如 '请做安全漏洞审计'..."
            className="flex-1 text-xs px-3 py-2 rounded-lg border bg-zinc-50 dark:bg-zinc-800/60 border-zinc-200 dark:border-zinc-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            data-testid="input-summon-text"
          />
          <button
            onClick={handleDispatchSummon}
            disabled={!detectedSpecialist}
            className={`flex items-center space-x-1.5 text-xs px-3.5 py-2 rounded-lg font-medium transition-colors ${
              detectedSpecialist
                ? 'bg-indigo-600 hover:bg-indigo-700 text-white cursor-pointer'
                : 'bg-zinc-200 dark:bg-zinc-800 text-zinc-400 cursor-not-allowed'
            }`}
            data-testid="btn-dispatch-summon"
          >
            <span>Summon</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleReset}
            aria-label="Reset state"
            className="p-2 rounded-lg border border-zinc-200 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500 transition-colors"
            data-testid="btn-reset"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
        {detectedSpecialist && (
          <div
            className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300"
            data-testid="detected-banner"
          >
            <span>
              Detected: <strong>{detectedSpecialist.name}</strong> ({triggerMode === 'explicit_mention' ? 'Explicit @-Tag' : 'Implicit Intent'})
            </span>
            <span className="text-[11px] font-mono">Isolated Sandbox Ready</span>
          </div>
        )}
      </div>

      {statusMessage && (
        <output
          className="text-xs p-2.5 rounded-lg mb-3 flex items-center space-x-2 border bg-zinc-100 dark:bg-zinc-800/60 border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300"
          data-testid="status-message"
        >
          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
          <span>{statusMessage}</span>
        </output>
      )}

      <div className="space-y-2 mb-2 max-h-44 overflow-y-auto">
        <div className="flex items-center justify-between text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          <span>Structured Aggregation Cards Bridged ({executions.length})</span>
          <span className="text-[10px] text-zinc-400 lowercase">Zero Parent Context Contamination</span>
        </div>
        {executions.length === 0 ? (
          <div className="text-xs text-zinc-400 py-3 text-center" data-testid="empty-executions">
            No active specialist executions yet. Try @-mention or typing intent keywords.
          </div>
        ) : (
          <div className="space-y-2" data-testid="executions-list">
            {executions.map((exec) => (
              <div
                key={exec.summon_id}
                className="p-3 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-800/40 text-xs"
                data-testid={`execution-item-${exec.summon_id}`}
              >
                <div className="flex items-center justify-between font-semibold mb-1 text-zinc-800 dark:text-zinc-200">
                  <div className="flex items-center space-x-1.5">
                    <FileCode className="w-3.5 h-3.5 text-indigo-500" />
                    <span>{exec.aggregation_card?.headline || exec.specialist_id}</span>
                  </div>
                  <span className="text-[11px] px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 font-mono">
                    {exec.status.toUpperCase()}
                  </span>
                </div>
                <div className="text-zinc-600 dark:text-zinc-400 text-[11px] mb-2">
                  {exec.aggregation_card?.deliverable_payload}
                </div>
                {exec.aggregation_card?.artifacts && exec.aggregation_card.artifacts.length > 0 && (
                  <div className="flex items-center space-x-1.5 text-[11px] text-zinc-500 font-mono">
                    <Users className="w-3 h-3 text-zinc-400" />
                    <span>Artifact: {exec.aggregation_card.artifacts.join(', ')}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </dialog>
  );
}
