'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { toast } from 'sonner';
import {
  Sparkles,
  ShieldAlert,
  CheckCircle2,
  Info,
} from 'lucide-react';
import {
  writebackService,
  type ReviewSlipBatch,
  type WritebackDecisionItem,
} from '@/services/wikiService';
import { useWikiAgentScope } from '../WikiAgentScopeContext';

interface WikiReviewSlipModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApplied?: () => void;
}

export function WikiReviewSlipModal({ open, onOpenChange, onApplied }: WikiReviewSlipModalProps) {
  const { agentScopeId } = useWikiAgentScope();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [batch, setBatch] = useState<ReviewSlipBatch | null>(null);
  const [userDecisions, setUserDecisions] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) {
      return;
    }

    const loadCandidates = async () => {
      setLoading(true);
      try {
        // 请求后端基于交付物洞察与负向规则合成审阅单
        const mockInsights = [
          {
            topic: '双写平滑迁移四部曲',
            content: '在不停机迁移过程中，按双写、校验、切换、断流四步推进，各步骤配置熔断指标。',
            rationale: '在核心系统交付中验证的高可用标准步骤，适用于未来类似架构重构。',
            recommended_layer: 'methods',
          },
          {
            topic: '云原生网关吞吐上限假说',
            content: '在单实例 4C8G 规格下，反向代理并发超过 15000 时出现内存抖动，需深入排查网卡驱动。',
            rationale: '属于待进一步压测论证的现象假说，不能直接作为客观真理。',
            recommended_layer: 'claims',
          },
          {
            topic: '预生产环境测试地址与端口',
            content: '测试节点内网地址为 192.168.10.15:9090，仅在本次压测中临时有效。',
            rationale: '单次测试数据',
          },
        ];

        const res = await writebackService.generateReviewSlips(
          {
            task_id: 'task_delivery_' + Date.now().toString(36),
            task_title: '任务交付经验萃取',
            candidate_insights: mockInsights,
          },
          agentScopeId,
        );

        setBatch(res);
        const initialSelections: Record<string, string> = {};
        for (const q of res.questions) {
          const rec = q.options.find((o) => o.recommended) || q.options[0];
          if (rec) {
            initialSelections[q.question_id] = rec.id;
          }
        }
        setUserDecisions(initialSelections);
      } catch (err) {
        console.error('Failed to generate review slips:', err);
        toast.error('获取审阅单失败');
      } finally {
        setLoading(false);
      }
    };

    void loadCandidates();
  }, [open, agentScopeId]);

  const handleApply = async () => {
    if (!batch || batch.questions.length === 0) {
      onOpenChange(false);
      return;
    }

    setSubmitting(true);
    try {
      const decisionItems: WritebackDecisionItem[] = batch.questions.map((q) => {
        const selectedId = userDecisions[q.question_id];
        const opt = q.options.find((o) => o.id === selectedId) || q.options[0];
        return {
          question_id: q.question_id,
          selected_option_id: opt.id,
          target_layer: opt.target_layer,
          candidate_title: q.topic,
          candidate_content: q.candidate_content,
        };
      });

      const res = await writebackService.applyWritebackDecisions(
        {
          task_id: batch.task_id,
          decisions: decisionItems,
        },
        agentScopeId,
      );

      toast.success(`选择性回写完成：已沉淀 ${res.committed_count} 项，跳过 ${res.discarded_count} 项`);
      onOpenChange(false);
      onApplied?.();
    } catch (err) {
      console.error('Failed to apply review slip writeback:', err);
      toast.error('应用选择性回写失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="p-6 pb-3 border-b border-border/40">
          <div className="flex items-center gap-2 text-primary font-medium text-xs">
            <Sparkles className="w-4 h-4" />
            <span>交付物知识沉淀引擎</span>
          </div>
          <DialogTitle className="text-xl font-bold mt-1">作者审阅单 (Review Slip)</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground mt-0.5">
            审查交付成果中萃取出的高价值洞察。杜绝全量回写污染知识库，由作者确认归属层级。
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {batch && batch.excluded_matches_count > 0 && (
            <div className="p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 flex items-start gap-3 text-xs">
              <ShieldAlert className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-emerald-700 dark:text-emerald-300">
                  负向规则已生效：已硬拦截 {batch.excluded_matches_count} 项瞬态杂质
                </span>
                <p className="text-muted-foreground mt-0.5 leading-relaxed">
                  系统已自动排除一次性测试 IP、虚拟配置、演示逐字稿与临时调试日志，保护知识库核心真理纯净度。
                </p>
              </div>
            </div>
          )}

          {loading ? (
            <div className="py-12 text-center text-xs text-muted-foreground">正在萃取高价值洞察并评估过滤规则...</div>
          ) : !batch || batch.questions.length === 0 ? (
            <div className="py-12 text-center text-xs text-muted-foreground">
              当前任务未产生需要回写的通用经验，全部内容已安全保留在交付物中。
            </div>
          ) : (
            batch.questions.map((q, idx) => {
              const currentChoice = userDecisions[q.question_id];
              return (
                <div
                  key={q.question_id}
                  className="p-4 rounded-xl border border-border/60 bg-card/60 shadow-sm space-y-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-mono font-bold">
                        {idx + 1}
                      </span>
                      <h4 className="text-sm font-semibold text-foreground">{q.topic}</h4>
                    </div>
                    <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
                      待定层级
                    </Badge>
                  </div>

                  <div className="p-2.5 rounded-lg bg-secondary/30 text-xs font-mono text-muted-foreground/90 border border-border/30 whitespace-pre-wrap">
                    {q.candidate_content}
                  </div>

                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground/80">
                    <Info className="w-3.5 h-3.5 text-primary shrink-0" />
                    <span>{q.rationale}</span>
                  </div>

                  <div className="pt-2 border-t border-border/30">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      {q.options.map((opt) => {
                        const isSelected = currentChoice === opt.id;
                        return (
                          <button
                            key={opt.id}
                            type="button"
                            onClick={() =>
                              setUserDecisions((prev) => ({
                                ...prev,
                                [q.question_id]: opt.id,
                              }))
                            }
                            className={`flex items-center justify-between p-2.5 rounded-lg border text-xs text-left cursor-pointer transition-all ${
                              isSelected
                                ? 'border-primary bg-primary/10 text-foreground font-medium ring-1 ring-primary/40 shadow-sm'
                                : 'border-border/40 hover:bg-secondary/40 text-muted-foreground'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <div
                                className={`w-3.5 h-3.5 rounded-full border flex items-center justify-center transition-colors ${
                                  isSelected ? 'border-primary bg-primary' : 'border-border/80'
                                }`}
                              >
                                {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-primary-foreground" />}
                              </div>
                              <span>{opt.label}</span>
                            </div>
                            {opt.recommended && (
                              <Badge variant="secondary" className="text-[9px] px-1 py-0 bg-primary/15 text-primary border-primary/20">
                                推荐
                              </Badge>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <DialogFooter className="p-4 border-t border-border/40 bg-secondary/10 flex items-center justify-between sm:justify-between">
          <span className="text-xs text-muted-foreground">
            提交后将写入对应层并打上 Draft 标签，由人工后续发布
          </span>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={submitting}>
              稍后再说
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={handleApply}
              disabled={submitting || loading || !batch || batch.questions.length === 0}
              className="gap-1.5 shadow-sm"
            >
              <CheckCircle2 className="w-4 h-4" />
              确认并安全回写
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
