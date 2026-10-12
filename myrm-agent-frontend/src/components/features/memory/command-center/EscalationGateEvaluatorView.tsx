/**
 * [INPUT]
 * @/services/memory/businessTemplates::evaluateEscalationGate, EscalationEvaluationRequest, EscalationEvaluationResponseDTO
 *
 * [OUTPUT]
 * EscalationGateEvaluatorView: Human escalation boundary gate evaluator and simulator.
 *
 * [POS]
 * Sub-view of Item 107 BusinessScenarioTemplatesCard.
 * Strict typing applied, zero any, file length < 350 lines.
 */

import React, { useState } from 'react';
import {
  ShieldAlert,
  Play,
  RotateCcw,
  Sparkles,
  UserCheck,
  Bot,
  AlertTriangle,
  Send,
  Zap,
} from 'lucide-react';
import type {
  EscalationEvaluationRequest,
  EscalationEvaluationResponseDTO,
} from '@/services/memory/businessTemplates';
import { evaluateEscalationGate } from '@/services/memory/businessTemplates';
import { FALLBACK_ESCALATION_EVALUATION_RESPONSE } from './businessTemplateFallbacks';

export const EscalationGateEvaluatorView: React.FC = () => {
  const [params, setParams] = useState<EscalationEvaluationRequest>({
    order_id: 'ORD-2026-X09',
    user_id: 'USR-8821',
    intent: '换货为XL尺码',
    shipment_status: 'delivered',
    is_custom_order: false,
    policy_clear: true,
    inventory_available: true,
    user_dispute_count: 0,
    warranty_valid: true,
    user_confirmed: false,
  });

  const [decision, setDecision] = useState<EscalationEvaluationResponseDTO | null>(
    FALLBACK_ESCALATION_EVALUATION_RESPONSE,
  );
  const [isEvaluating, setIsEvaluating] = useState(false);

  const applyPreset = (presetKey: 'custom' | 'out_of_stock' | 'dispute' | 'clean_flow') => {
    if (presetKey === 'custom') {
      setParams((prev) => ({
        ...prev,
        is_custom_order: true,
        policy_clear: false,
        inventory_available: true,
        user_dispute_count: 0,
      }));
    } else if (presetKey === 'out_of_stock') {
      setParams((prev) => ({
        ...prev,
        is_custom_order: false,
        policy_clear: true,
        inventory_available: false,
        user_dispute_count: 0,
      }));
    } else if (presetKey === 'dispute') {
      setParams((prev) => ({
        ...prev,
        is_custom_order: false,
        policy_clear: true,
        inventory_available: true,
        user_dispute_count: 2,
      }));
    } else {
      setParams((prev) => ({
        ...prev,
        is_custom_order: false,
        policy_clear: true,
        inventory_available: true,
        user_dispute_count: 0,
        user_confirmed: true,
      }));
    }
  };

  const handleEvaluate = async () => {
    setIsEvaluating(true);
    try {
      const res = await evaluateEscalationGate(params);
      setDecision(res);
    } catch {
      // Local fallback simulation calculation
      if (params.is_custom_order || !params.policy_clear) {
        setDecision({
          action: 'escalate_to_human',
          reason: 'policy_ambiguity',
          message: '订单涉及定制品类或政策模糊，已触发人工审核拦截。',
          required_context: { order_id: params.order_id || 'unknown', issue: 'custom_order' },
          suggested_skill_or_tool: 'route_to_human_specialist',
        });
      } else if (!params.inventory_available) {
        setDecision({
          action: 'escalate_to_human',
          reason: 'inventory_shortage',
          message: '更换目标SKU断码缺货，无法自主发货，转人工协商。',
          required_context: { order_id: params.order_id || 'unknown', stock: 'out_of_stock' },
          suggested_skill_or_tool: 'escalate_out_of_stock_case',
        });
      } else if ((params.user_dispute_count ?? 0) >= 2) {
        setDecision({
          action: 'escalate_to_human',
          reason: 'user_dispute_failed',
          message: '用户纠偏已达2次以上，防死循环争论熔断并转人工。',
          required_context: { dispute_count: String(params.user_dispute_count) },
          suggested_skill_or_tool: 'connect_dispute_arbitrator',
        });
      } else {
        setDecision({
          action: 'proceed_automated',
          reason: 'none',
          message: params.user_confirmed
            ? '所有条件满足且用户已确认，允许自主调用办理工具。'
            : '前置条件满足，请等待用户显式确认。',
          required_context: { order_id: params.order_id || 'unknown' },
          suggested_skill_or_tool: params.user_confirmed
            ? 'commit_retail_exchange'
            : 'request_user_confirmation',
        });
      }
    } finally {
      setIsEvaluating(false);
    }
  };

  const isEscalation = decision?.action === 'escalate_to_human';

  return (
    <div className="space-y-4">
      {/* Quick Presets Bar */}
      <div className="flex flex-wrap items-center gap-2 p-2.5 bg-muted/30 rounded-lg border border-border/50">
        <span className="text-xs font-medium text-muted-foreground mr-1 flex items-center gap-1">
          <Zap className="w-3.5 h-3.5 text-amber-500" />
          快速仿真预设:
        </span>
        <button
          type="button"
          onClick={() => applyPreset('custom')}
          className="px-2 py-1 text-xs font-medium rounded bg-background border border-border hover:bg-muted text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
        >
          定制/政策模糊
        </button>
        <button
          type="button"
          onClick={() => applyPreset('out_of_stock')}
          className="px-2 py-1 text-xs font-medium rounded bg-background border border-border hover:bg-muted text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
        >
          SKU缺货断码
        </button>
        <button
          type="button"
          onClick={() => applyPreset('dispute')}
          className="px-2 py-1 text-xs font-medium rounded bg-background border border-border hover:bg-muted text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
        >
          用户争议纠正熔断
        </button>
        <button
          type="button"
          onClick={() => applyPreset('clean_flow')}
          className="px-2 py-1 text-xs font-medium rounded bg-background border border-border hover:bg-muted text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
        >
          标准合规流(放行)
        </button>
      </div>

      {/* Interactive Form & Evaluation Output Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left: Input Parameters Form */}
        <div className="p-3.5 bg-background rounded-lg border border-border/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-primary" />
              业务与客户上下文参数
            </span>
            <button
              type="button"
              onClick={handleEvaluate}
              disabled={isEvaluating}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <Play className="w-3.5 h-3.5" />
              {isEvaluating ? '评估中...' : '评估门禁'}
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2.5 text-xs">
            <div>
              <label htmlFor="escalation-order-id" className="text-muted-foreground block text-[11px] mb-1">
                订单编号
              </label>
              <input
                id="escalation-order-id"
                type="text"
                value={params.order_id || ''}
                onChange={(e) => setParams({ ...params, order_id: e.target.value })}
                className="w-full px-2 py-1 rounded bg-muted/40 border border-border focus:outline-none focus:ring-2 focus:ring-primary font-mono text-xs"
              />
            </div>
            <div>
              <label htmlFor="escalation-dispute-count" className="text-muted-foreground block text-[11px] mb-1">
                用户纠错/争议次数
              </label>
              <input
                id="escalation-dispute-count"
                type="number"
                min={0}
                max={5}
                value={params.user_dispute_count ?? 0}
                onChange={(e) =>
                  setParams({ ...params, user_dispute_count: Number(e.target.value) })
                }
                className="w-full px-2 py-1 rounded bg-muted/40 border border-border focus:outline-none focus:ring-2 focus:ring-primary font-mono text-xs"
              />
            </div>
          </div>

          <div className="space-y-2 pt-1 border-t border-border/40 text-xs">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={params.is_custom_order}
                onChange={(e) =>
                  setParams({ ...params, is_custom_order: e.target.checked })
                }
                className="rounded border-border text-primary focus:ring-primary"
              />
              <span>涉及定制特殊商品 (is_custom_order)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={params.policy_clear}
                onChange={(e) =>
                  setParams({ ...params, policy_clear: e.target.checked })
                }
                className="rounded border-border text-primary focus:ring-primary"
              />
              <span>退换货政策清晰无争议 (policy_clear)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={params.inventory_available}
                onChange={(e) =>
                  setParams({ ...params, inventory_available: e.target.checked })
                }
                className="rounded border-border text-primary focus:ring-primary"
              />
              <span>目标更换SKU有库存 (inventory_available)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={params.user_confirmed}
                onChange={(e) =>
                  setParams({ ...params, user_confirmed: e.target.checked })
                }
                className="rounded border-border text-primary focus:ring-primary"
              />
              <span>用户已显式确认换货规格 (user_confirmed)</span>
            </label>
          </div>
        </div>

        {/* Right: Decision Output & Human Handover Package */}
        <div className="p-3.5 bg-background rounded-lg border border-border/60 flex flex-col justify-between space-y-3">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                门禁决策评估结果
              </span>
              {decision && (
                <span
                  className={`text-[11px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 ${
                    isEscalation
                      ? 'bg-destructive/10 text-destructive border border-destructive/20'
                      : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                  }`}
                >
                  {isEscalation ? (
                    <UserCheck className="w-3 h-3" />
                  ) : (
                    <Bot className="w-3 h-3" />
                  )}
                  {decision.action.toUpperCase()}
                </span>
              )}
            </div>

            {decision ? (
              <div className="space-y-2 text-xs">
                <div className="p-2.5 rounded bg-muted/30 border border-border/50 space-y-1">
                  <div className="text-[11px] font-mono text-muted-foreground flex items-center gap-1">
                    <span>触发原因分类:</span>
                    <strong className="text-foreground">{decision.reason}</strong>
                  </div>
                  <p className="text-xs text-foreground leading-relaxed">
                    {decision.message}
                  </p>
                </div>

                <div className="p-2.5 rounded bg-muted/20 border border-border/40 space-y-1">
                  <span className="text-[11px] font-mono text-muted-foreground block">
                    推荐下一步处理动作:
                  </span>
                  <code className="text-xs font-mono text-primary font-semibold">
                    {decision.suggested_skill_or_tool}
                  </code>
                </div>

                {isEscalation && (
                  <div className="p-2 bg-destructive/5 rounded border border-destructive/15 text-[11px] text-destructive flex items-start gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>
                      已阻断自主办理并生成人工交接数据包，Agent自动切为只读辅助。
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground py-8 text-center">
                点击左侧“评估门禁”查看实时决策判定
              </div>
            )}
          </div>

          <div className="text-[10px] text-muted-foreground font-mono pt-2 border-t border-border/40">
            OpenViking & τ²-bench 真实场景双重防护门禁
          </div>
        </div>
      </div>
    </div>
  );
};
