/**
 * Conclusion Attribution and Verifiable Chat Evidence Studio Card (Item 141).
 * Interactive dashboard providing bidirectional causality trees, ripple impact analysis,
 * and on-demand transparent chat evidence packages.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Network,
  ShieldCheck,
  ArrowDownCircle,
  ArrowUpCircle,
  AlertTriangle,
  Trash2,
  MessageSquare,
  RefreshCw,
  Sparkles,
  CheckCircle2,
} from 'lucide-react';
import {
  conclusionAttributionApi,
  AttributedConclusionDTO,
  AttributionMetricsResponse,
  ChatEvidenceDTO,
  RippleImpactResponse,
  GraphTraversalNodeDTO,
} from '@/services/memory/conclusionAttribution';

const mockMetrics: AttributionMetricsResponse = {
  total_conclusions: 3,
  explicit_count: 2,
  deductive_count: 1,
  inductive_count: 0,
  contradiction_count: 0,
  max_derivation_depth: 1,
  average_times_derived: 1.33,
};

const mockConclusions: AttributedConclusionDTO[] = [
  {
    id: 'conc_root_1',
    peer_id: 'alice',
    content: 'Alice 倾向使用 2 空格紧凑代码缩进与严格类型提示',
    level: 'explicit',
    source_ids: [],
    times_derived: 2,
    confidence: 0.95,
    created_at: new Date().toISOString(),
  },
  {
    id: 'conc_root_2',
    peer_id: 'alice',
    content: 'Alice 要求代码库严禁使用 Any 类型逃逸检查',
    level: 'explicit',
    source_ids: [],
    times_derived: 1,
    confidence: 0.98,
    created_at: new Date().toISOString(),
  },
  {
    id: 'conc_derived_1',
    peer_id: 'alice',
    content: '代码审查时自动强化 Any 类型拦截器并在 CI 中开启 strictNullChecks',
    level: 'deductive',
    source_ids: ['conc_root_1', 'conc_root_2'],
    times_derived: 1,
    confidence: 0.92,
    created_at: new Date().toISOString(),
  },
];

interface ConclusionAttributionStudioCardProps {
  className?: string;
}

export const ConclusionAttributionStudioCard: React.FC<
  ConclusionAttributionStudioCardProps
> = ({ className = '' }) => {
  const [metrics, setMetrics] = useState<AttributionMetricsResponse>(mockMetrics);
  const [conclusions, setConclusions] = useState<AttributedConclusionDTO[]>(mockConclusions);
  const [filterLevel, setFilterLevel] = useState<string>('all');
  const [selectedConclusion, setSelectedConclusion] = useState<AttributedConclusionDTO | null>(null);
  const [traversalNodes, setTraversalNodes] = useState<GraphTraversalNodeDTO[]>([]);
  const [traversalDirection, setTraversalDirection] = useState<'downward' | 'upward' | null>(null);
  const [rippleReport, setRippleReport] = useState<RippleImpactResponse | null>(null);
  const [chatQuery, setChatQuery] = useState('');
  const [chatReply, setChatReply] = useState<string | null>(null);
  const [chatEvidence, setChatEvidence] = useState<ChatEvidenceDTO | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const loadData = useCallback(async () => {
    try {
      const [statsRes, listRes] = await Promise.all([
        conclusionAttributionApi.getStats(),
        conclusionAttributionApi.listConclusions(),
      ]);
      setMetrics(statsRes);
      if (listRes.items.length > 0) {
        setConclusions(listRes.items);
      }
    } catch {
      setMetrics(mockMetrics);
      setConclusions(mockConclusions);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleWalkDownward = async (c: AttributedConclusionDTO) => {
    setIsLoading(true);
    try {
      const res = await conclusionAttributionApi.walkDownwardTree(c.id);
      setSelectedConclusion(c);
      setTraversalNodes(res.nodes);
      setTraversalDirection('downward');
      setRippleReport(null);
      showToast(`已加载【${c.id}】向下溯源前提树（${res.total_nodes} 节点）`);
    } catch {
      showToast('获取向下溯源前提失败，当前显示本地缓存');
    } finally {
      setIsLoading(false);
    }
  };

  const handleWalkUpward = async (c: AttributedConclusionDTO) => {
    setIsLoading(true);
    try {
      const res = await conclusionAttributionApi.walkUpwardTree(c.id);
      setSelectedConclusion(c);
      setTraversalNodes(res.nodes);
      setTraversalDirection('upward');
      setRippleReport(null);
      showToast(`已加载【${c.id}】向上派生推论树（${res.total_nodes} 节点）`);
    } catch {
      showToast('获取向上派生推论失败');
    } finally {
      setIsLoading(false);
    }
  };

  const handleInspectRipple = async (c: AttributedConclusionDTO) => {
    setIsLoading(true);
    try {
      const res = await conclusionAttributionApi.getRippleImpact(c.id);
      setSelectedConclusion(c);
      setRippleReport(res);
      setTraversalDirection(null);
      showToast(`涟漪影响分析完成：等级【${res.severity.toUpperCase()}】`);
    } catch {
      showToast('获取涟漪影响报告失败');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (c: AttributedConclusionDTO, cascade: boolean) => {
    if (!window.confirm(`确定删除结论【${c.id}】？(级联模式: ${cascade ? '是' : '否'})`)) {
      return;
    }
    setIsLoading(true);
    try {
      await conclusionAttributionApi.deleteConclusion(c.id, cascade);
      showToast(`已成功删除结论【${c.id}】`);
      loadData();
    } catch {
      setConclusions((prev) => prev.filter((it) => it.id !== c.id));
      showToast(`已在视图中移除结论【${c.id}】`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSimulateChat = async () => {
    if (!chatQuery.trim()) return;
    setIsLoading(true);
    try {
      const res = await conclusionAttributionApi.chatWithEvidence({
        query: chatQuery,
        peer_id: 'alice',
        include_evidence: true,
      });
      setChatReply(res.reply);
      setChatEvidence(res.evidence || null);
      showToast('已完成带证据链推理回答');
    } catch {
      setChatReply(`基于显式记忆：用户严禁使用 Any 类型 [explicit]`);
      setChatEvidence({
        conclusions: mockConclusions.slice(0, 1),
        messages: [{
          message_id: 'mock_msg_1',
          session_id: 'sess_fallback',
          role: 'user',
          snippet: chatQuery,
        }],
        tool_calls: [{
          tool_name: 'query_conclusions',
          tool_input: { query: chatQuery },
          tool_output_snippet: '1 conclusion matched',
        }],
      });
      showToast('使用降级证据链模拟响应');
    } finally {
      setIsLoading(false);
    }
  };

  const filteredItems = conclusions.filter((c) => {
    if (filterLevel === 'all') return true;
    return c.level.toLowerCase() === filterLevel.toLowerCase();
  });

  return (
    <div className={`p-5 bg-card border rounded-xl shadow-sm space-y-5 ${className}`}>
      {/* 头部导航与标题 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Network className="w-5 h-5 text-indigo-500" />
          <h3 className="font-semibold text-foreground text-base">
            记忆结论归因与证据链可视化工作台
          </h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-500 font-mono">
            Item 141 · P1
          </span>
        </div>
        <button
          type="button"
          onClick={loadData}
          disabled={isLoading}
          aria-label="刷新归因数据"
          className="p-1.5 hover:bg-muted rounded-md text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* 提示消息 */}
      {toastMessage && (
        <div className="flex items-center gap-2 text-xs py-2 px-3 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-lg border border-emerald-500/20">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* HUD 统计指标栏 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
          <div className="text-xs text-muted-foreground">结论总数</div>
          <div className="text-xl font-bold mt-1 text-foreground">{metrics.total_conclusions}</div>
        </div>
        <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
          <div className="text-xs text-muted-foreground">直接事实 / 衍生推论</div>
          <div className="text-xl font-bold mt-1 text-emerald-600 dark:text-emerald-400">
            {metrics.explicit_count} <span className="text-xs text-muted-foreground font-normal">/ {metrics.deductive_count + metrics.inductive_count}</span>
          </div>
        </div>
        <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
          <div className="text-xs text-muted-foreground">最大推导深度</div>
          <div className="text-xl font-bold mt-1 text-indigo-600 dark:text-indigo-400">
            {metrics.max_derivation_depth} <span className="text-xs text-muted-foreground font-normal">层</span>
          </div>
        </div>
        <div className="p-3 bg-muted/40 rounded-lg border border-border/50">
          <div className="text-xs text-muted-foreground">平均印证次数</div>
          <div className="text-xl font-bold mt-1 text-amber-600 dark:text-amber-400">
            {metrics.average_times_derived} <span className="text-xs text-muted-foreground font-normal">次</span>
          </div>
        </div>
      </div>

      {/* 筛选与列表视图 */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-xs font-medium text-muted-foreground">归因分级筛选</div>
          <div className="flex gap-1.5 text-xs">
            {['all', 'explicit', 'deductive', 'inductive'].map((lvl) => (
              <button
                key={lvl}
                type="button"
                onClick={() => setFilterLevel(lvl)}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterLevel === lvl
                    ? 'bg-primary text-primary-foreground font-medium'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
              >
                {lvl === 'all' ? '全部' : lvl.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* 结论卡片列表 */}
        <div className="space-y-2">
          {filteredItems.map((c) => (
            <div
              key={c.id}
              className="p-3.5 bg-background border rounded-lg hover:border-primary/40 transition-colors space-y-2"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                        c.level === 'explicit'
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                          : 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20'
                      }`}
                    >
                      {c.level.toUpperCase()}
                    </span>
                    <span className="text-xs text-muted-foreground font-mono">{c.id}</span>
                    <span className="text-[11px] text-muted-foreground">印证 {c.times_derived} 次</span>
                    <span className="text-[11px] text-muted-foreground">置信度 {(c.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="text-sm font-medium text-foreground">{c.content}</div>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => handleWalkDownward(c)}
                    aria-label={`查看${c.id}前提树`}
                    title="向下追踪前提 (Walk Downward)"
                    className="p-1.5 hover:bg-muted rounded text-muted-foreground hover:text-indigo-500 transition-colors"
                  >
                    <ArrowDownCircle className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleWalkUpward(c)}
                    aria-label={`查看${c.id}派生树`}
                    title="向上追踪派生 (Walk Upward)"
                    className="p-1.5 hover:bg-muted rounded text-muted-foreground hover:text-indigo-500 transition-colors"
                  >
                    <ArrowUpCircle className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleInspectRipple(c)}
                    aria-label={`评估${c.id}涟漪影响`}
                    title="涟漪影响评估 (Ripple Impact)"
                    className="p-1.5 hover:bg-muted rounded text-muted-foreground hover:text-amber-500 transition-colors"
                  >
                    <AlertTriangle className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(c, false)}
                    aria-label={`删除${c.id}`}
                    title="安全删除 (Delete)"
                    className="p-1.5 hover:bg-muted rounded text-muted-foreground hover:text-destructive transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 双向图遍历与涟漪分析展示区 */}
      {(traversalDirection || rippleReport) && selectedConclusion && (
        <div className="p-4 bg-muted/30 border rounded-lg space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-primary" />
              <div className="text-xs font-semibold text-foreground">
                {traversalDirection === 'downward' && `向下前提溯源树 · ${selectedConclusion.id}`}
                {traversalDirection === 'upward' && `向上派生推论树 · ${selectedConclusion.id}`}
                {rippleReport && `修改/撤回涟漪影响评估 · ${selectedConclusion.id}`}
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                setTraversalDirection(null);
                setRippleReport(null);
              }}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              关闭
            </button>
          </div>

          {traversalDirection && (
            <div className="space-y-1.5">
              {traversalNodes.map((n, idx) => (
                <div
                  key={`${n.conclusion.id}_${idx}`}
                  style={{ marginLeft: `${n.depth * 16}px` }}
                  className="flex items-center gap-2 text-xs py-1 px-2.5 bg-background border rounded font-mono"
                >
                  <span className="text-muted-foreground">L{n.depth}</span>
                  <span className="font-semibold text-foreground">{n.conclusion.id}</span>
                  <span className="text-muted-foreground">[{n.conclusion.level}]</span>
                  <span className="text-foreground truncate">{n.conclusion.content}</span>
                </div>
              ))}
            </div>
          )}

          {rippleReport && (
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">风险等级:</span>
                <span className={`px-2 py-0.5 rounded font-bold font-mono ${
                  rippleReport.severity === 'critical' || rippleReport.severity === 'high'
                    ? 'bg-destructive/10 text-destructive'
                    : 'bg-emerald-500/10 text-emerald-600'
                }`}>
                  {rippleReport.severity.toUpperCase()}
                </span>
                <span className="text-muted-foreground">波及推论数:</span>
                <span className="font-mono font-bold text-foreground">{rippleReport.impacted_conclusion_ids.length}</span>
              </div>
              <p className="text-muted-foreground">{rippleReport.explanation}</p>
            </div>
          )}
        </div>
      )}

      {/* 对话证据链透明度试运行栏 */}
      <div className="p-4 bg-muted/20 border rounded-lg space-y-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-indigo-500" />
          <div className="text-xs font-semibold text-foreground">按需透明 ChatEvidence 证据链试运行</div>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={chatQuery}
            onChange={(e) => setChatQuery(e.target.value)}
            placeholder="输入测试提问（例如：代码风格偏好是什么？）"
            className="flex-1 text-xs px-3 py-2 bg-background border rounded-lg focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <button
            type="button"
            onClick={handleSimulateChat}
            disabled={isLoading || !chatQuery.trim()}
            className="px-3.5 py-2 text-xs bg-primary text-primary-foreground font-medium rounded-lg hover:bg-primary/90 transition-colors flex items-center gap-1.5"
          >
            <Sparkles className="w-3.5 h-3.5" />
            透明推理
          </button>
        </div>

        {chatReply && (
          <div className="p-3 bg-background border rounded-lg space-y-2 text-xs">
            <div className="font-semibold text-foreground">Agent 响应：</div>
            <p className="text-muted-foreground">{chatReply}</p>
            {chatEvidence && (
              <div className="pt-2 border-t space-y-1.5 font-mono text-[11px]">
                <div className="text-indigo-600 dark:text-indigo-400 font-semibold">
                  📦 Verifiable Evidence Package ({chatEvidence.conclusions.length} 条依据结论 / {chatEvidence.messages.length} 条溯源消息)
                </div>
                {chatEvidence.conclusions.map((ec) => (
                  <div key={ec.id} className="text-muted-foreground pl-2 border-l-2 border-indigo-500/30">
                    • [{ec.level}] {ec.content} (times: {ec.times_derived})
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
