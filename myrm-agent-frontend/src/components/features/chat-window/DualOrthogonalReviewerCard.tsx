import React, { useState } from 'react';
import { ArbiterVerdictSummaryView } from './orthogonal-reviewer/ArbiterVerdictSummaryView';
import { DualReviewerSplitView } from './orthogonal-reviewer/DualReviewerSplitView';
import {
  type ArbiterVerdict,
  INITIAL_MOCK_ARBITER_VERDICT,
  INITIAL_MOCK_REVIEWER_A,
  INITIAL_MOCK_REVIEWER_B,
  type ReviewerReport,
} from './orthogonal-reviewer/types';

export const DualOrthogonalReviewerCard: React.FC = () => {
  const [reviewerA, setReviewerA] = useState<ReviewerReport>(INITIAL_MOCK_REVIEWER_A);
  const [reviewerB, setReviewerB] = useState<ReviewerReport>(INITIAL_MOCK_REVIEWER_B);
  const [verdict, setVerdict] = useState<ArbiterVerdict>(INITIAL_MOCK_ARBITER_VERDICT);
  const [statusMessage, setStatusMessage] = useState<string>(
    '正交双视角审查门禁已就绪：Reviewer A 意图核验与 Reviewer B 盲态无偏代码审查并行守护。',
  );

  // Scenario Simulator
  const handleSelectScenario = (scenario: 'clean' | 'intent_drift' | 'blind_safety' | 'double_blocker') => {
    if (scenario === 'clean') {
      setReviewerA(INITIAL_MOCK_REVIEWER_A);
      setReviewerB(INITIAL_MOCK_REVIEWER_B);
      setVerdict(INITIAL_MOCK_ARBITER_VERDICT);
      setStatusMessage('场景切换：双重视角均绿灯通过，仲裁器已核发准入凭据 (ADMITTED)。');
    } else if (scenario === 'intent_drift') {
      const updatedA: ReviewerReport = {
        reviewer_id: 'reviewer-a-intent-gate',
        perspective: 'intent_alignment',
        passed: false,
        summary: 'Reviewer A 拦截：检测到功能偏离，未能完整覆盖任务要求的持久化对账机制。',
        is_clean_context: false,
        findings: [
          {
            finding_id: 'find-drift-01',
            reviewer_role: 'reviewer_a_intent',
            file_path: 'app/services/agent/sync_service.py',
            line_range: [45, 60],
            severity: 'critical',
            category: 'intent_drift',
            title: '偏离原始持久化要求',
            description: '任务要求使用 CAS 乐观对账并落盘，代码中仅使用了内存字典保存。',
            suggested_action: '重构 sync_service.py，使用 DB 事务与 CAS 版本列完成落盘。',
          },
        ],
      };
      setReviewerA(updatedA);
      setReviewerB(INITIAL_MOCK_REVIEWER_B);
      setVerdict({
        session_id: 'session-review-demo-001',
        decision: 'blocked',
        total_findings_count: 1,
        critical_count: 1,
        major_count: 0,
        minor_count: 0,
        blocker_reasons: ['Reviewer A: [INTENT_DRIFT] 偏离原始持久化要求，缺少落盘对账机制。'],
        deduplicated_findings: updatedA.findings,
        auto_fix_prompts: [
          'FIX(intent_drift): app/services/agent/sync_service.py:45-60 -> 重构 sync_service.py，使用 DB 事务与 CAS 版本列完成落盘。',
        ],
        reviewer_a_summary: updatedA.summary,
        reviewer_b_summary: INITIAL_MOCK_REVIEWER_B.summary,
      });
      setStatusMessage('警报：Reviewer A 意图核验未通过，阻断门禁生效，已生成自愈修复指令！');
    } else if (scenario === 'blind_safety') {
      const updatedB: ReviewerReport = {
        reviewer_id: 'reviewer-b-blind-gate',
        perspective: 'blind_clean_context',
        passed: false,
        summary: 'Reviewer B (盲态独立子智能体) 拦截：发现严苛红线违规，存在 Any 类型逃逸与未受控除法。',
        is_clean_context: true,
        findings: [
          {
            finding_id: 'find-blind-01',
            reviewer_role: 'reviewer_b_blind',
            file_path: 'app/schemas/payload.py',
            line_range: [18, 22],
            severity: 'critical',
            category: 'type_safety',
            title: '禁止使用 Any 类型',
            description: '检测到 payload: Any 破坏了系统严格类型安全契约红线。',
            suggested_action: '替换 Any 为精确的 Pydantic 泛型或 Union[DataModel, ErrorModel]。',
          },
          {
            finding_id: 'find-blind-02',
            reviewer_role: 'reviewer_b_blind',
            file_path: 'app/utils/calc.py',
            line_range: [88, 92],
            severity: 'major',
            category: 'boundary_edge_case',
            title: '未防除零异常',
            description: '未对除数 total_count 做 <= 0 边界卫语句检查。',
            suggested_action: '添加 if total_count <= 0: return 0.0 边界防御。',
          },
        ],
      };
      setReviewerA(INITIAL_MOCK_REVIEWER_A);
      setReviewerB(updatedB);
      setVerdict({
        session_id: 'session-review-demo-001',
        decision: 'blocked',
        total_findings_count: 2,
        critical_count: 1,
        major_count: 1,
        minor_count: 0,
        blocker_reasons: [
          'Reviewer B (Blind): [TYPE_SAFETY] 禁止使用 Any 类型，契约安全被破坏。',
          'Reviewer B (Blind): [BOUNDARY_EDGE_CASE] 未防除零异常。',
        ],
        deduplicated_findings: updatedB.findings,
        auto_fix_prompts: [
          'FIX(type_safety): app/schemas/payload.py:18-22 -> 替换 Any 为精确的 Pydantic 泛型或 Union[DataModel, ErrorModel]。',
          'FIX(boundary_edge_case): app/utils/calc.py:88-92 -> 添加 if total_count <= 0: return 0.0 边界防御。',
        ],
        reviewer_a_summary: INITIAL_MOCK_REVIEWER_A.summary,
        reviewer_b_summary: updatedB.summary,
      });
      setStatusMessage('警报：Reviewer B 盲审拦截类型逃逸与边界隐患，零偏见哨兵有效杜绝了先验偏见放行！');
    } else {
      // Double Blocker
      const findingsA = [
        {
          finding_id: 'find-drift-01',
          reviewer_role: 'reviewer_a_intent' as const,
          file_path: 'app/services/agent/sync_service.py',
          line_range: [45, 60] as [number, number],
          severity: 'critical' as const,
          category: 'intent_drift' as const,
          title: '偏离原始持久化要求',
          description: '缺少落盘对账机制。',
          suggested_action: '使用 DB 事务与 CAS 版本列落盘。',
        },
      ];
      const findingsB = [
        {
          finding_id: 'find-blind-01',
          reviewer_role: 'reviewer_b_blind' as const,
          file_path: 'app/schemas/payload.py',
          line_range: [18, 22] as [number, number],
          severity: 'critical' as const,
          category: 'type_safety' as const,
          title: '禁止使用 Any 类型',
          description: 'Any 类型逃逸。',
          suggested_action: '替换 Any 为精确类型。',
        },
      ];
      setReviewerA({
        ...INITIAL_MOCK_REVIEWER_A,
        passed: false,
        summary: 'Reviewer A 严重阻断：意图发生实质漂移。',
        findings: findingsA,
      });
      setReviewerB({
        ...INITIAL_MOCK_REVIEWER_B,
        passed: false,
        summary: 'Reviewer B 严重阻断：盲审检测到致命类型违规。',
        findings: findingsB,
      });
      setVerdict({
        session_id: 'session-review-demo-001',
        decision: 'blocked',
        total_findings_count: 2,
        critical_count: 2,
        major_count: 0,
        minor_count: 0,
        blocker_reasons: [
          'Reviewer A: [INTENT_DRIFT] 缺少落盘对账机制。',
          'Reviewer B: [TYPE_SAFETY] 禁止使用 Any 类型。',
        ],
        deduplicated_findings: [...findingsA, ...findingsB],
        auto_fix_prompts: [
          'FIX(intent_drift): app/services/agent/sync_service.py:45-60 -> 使用 DB 事务与 CAS 版本列落盘。',
          'FIX(type_safety): app/schemas/payload.py:18-22 -> 替换 Any 为精确类型。',
        ],
        reviewer_a_summary: 'Reviewer A 严重阻断：意图发生实质漂移。',
        reviewer_b_summary: 'Reviewer B 严重阻断：盲审检测到致命类型违规。',
      });
      setStatusMessage('严重警报：双审双重视角均触发 Critical 阻断，系统禁止合流！');
    }
  };

  const handleDispatchAutoFix = (prompt: string) => {
    setStatusMessage(`已派发自愈修复指令: ${prompt.slice(0, 60)}...`);
  };

  return (
    <article
      data-testid="dual-orthogonal-reviewer-card"
      aria-label="正交双视角审查门禁与零偏见盲审子代理控制台"
      className="my-3 flex flex-col gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-950 sm:p-5"
    >
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 pb-3 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-100 text-base dark:bg-purple-950/60">
            ⚖️
          </span>
          <div>
            <h2 className="text-sm font-bold text-gray-900 dark:text-gray-100">
              DualOrthogonalReviewerGateWithBlindCleanContextSubagent
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              正交双重视角审查 · Reviewer A 意图一致性 vs Reviewer B 盲态独立代码审查 · 去重仲裁与自动修复
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-full bg-purple-50 px-2.5 py-0.5 text-xs font-semibold text-purple-700 dark:bg-purple-950/50 dark:text-purple-300">
            P0 质量门禁守卫
          </span>
        </div>
      </header>

      {/* Interactive Scenario Presets */}
      <section aria-label="场景预设模拟调试" className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-bold text-gray-600 dark:text-gray-400">模拟审查场景:</span>
        <button
          type="button"
          onClick={() => handleSelectScenario('clean')}
          className="rounded border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 transition hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
        >
          双审全通 (Admitted)
        </button>
        <button
          type="button"
          onClick={() => handleSelectScenario('intent_drift')}
          className="rounded border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-800 transition hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-300"
        >
          意图偏离拦截 (Drift)
        </button>
        <button
          type="button"
          onClick={() => handleSelectScenario('blind_safety')}
          className="rounded border border-purple-200 bg-purple-50 px-2.5 py-1 text-xs font-medium text-purple-800 transition hover:bg-purple-100 dark:border-purple-800 dark:bg-purple-950/40 dark:text-purple-300"
        >
          盲审类型拦截 (Type/Bound)
        </button>
        <button
          type="button"
          onClick={() => handleSelectScenario('double_blocker')}
          className="rounded border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-800 transition hover:bg-rose-100 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300"
        >
          双重致命阻断 (Double Block)
        </button>
      </section>

      {/* Split Views for Reviewer A and Reviewer B */}
      <DualReviewerSplitView reviewerA={reviewerA} reviewerB={reviewerB} />

      {/* Unified Arbiter Verdict and Auto Fix Dispatch */}
      <ArbiterVerdictSummaryView verdict={verdict} onDispatchAutoFix={handleDispatchAutoFix} />

      {/* Accessibility Status Output */}
      <footer className="border-t border-gray-100 pt-3 dark:border-gray-800">
        <output
          data-testid="orthogonal-reviewer-status-live"
          aria-live="polite"
          className="block text-xs font-medium text-gray-600 dark:text-gray-300"
        >
          {statusMessage}
        </output>
      </footer>
    </article>
  );
};
