import { create } from 'zustand';
import type {
  DynamicFormSpec,
  FormFieldValue,
  GenUIReconciliationState,
  ReconciliationOutcome,
} from './genuiReconciliationTypes';
import { reconcileAnswersWithSpec } from './reconciliationGuard';

const INITIAL_SPEC: DynamicFormSpec = {
  specId: 'spec-approval-rollout-v1',
  version: 1,
  title: '生产级无损金丝雀灰度发布审批',
  description: '由 Agent 动态分析服务依赖后下发的参数表单，支持流式规格调和',
  pushedAt: new Date().toISOString(),
  fields: [
    {
      fieldId: 'cluster_name',
      label: '目标集群名称',
      type: 'text',
      defaultValue: 'k8s-edge-shanghai-01',
      description: '执行灰度发布的目标 K8s 集群标识',
      required: true,
    },
    {
      fieldId: 'replica_count',
      label: '初始 Pod 副本数量',
      type: 'number',
      defaultValue: 3,
      description: '部署的保底健康实例数',
      required: true,
    },
    {
      fieldId: 'routing_policy',
      label: '流量分发策略',
      type: 'select',
      defaultValue: 'header_weighted',
      description: '入口网关流量染色匹配规则',
      options: [
        { label: 'Header 权重分流 (header_weighted)', value: 'header_weighted' },
        { label: 'Cookie 粘性会话 (cookie_affinity)', value: 'cookie_affinity' },
        { label: '全量盲切 (all_or_nothing)', value: 'all_or_nothing' },
      ],
      required: true,
    },
    {
      fieldId: 'auto_rollback_on_slo_breach',
      label: 'SLO 劣化自动熔断回滚',
      type: 'boolean',
      defaultValue: true,
      description: '当 P99 延迟超过 200ms 或 5xx 错误率 > 0.1% 时自动撤销发布',
    },
  ],
};

function buildInitialAnswers(spec: DynamicFormSpec) {
  const initial: Record<string, FormFieldValue> = {};
  for (const field of spec.fields) {
    initial[field.fieldId] = field.defaultValue;
  }
  return initial;
}

export const useGenUIAnswersReconciliationStore = create<GenUIReconciliationState>(
  (set, get) => ({
    currentSpec: INITIAL_SPEC,
    answers: buildInitialAnswers(INITIAL_SPEC),
    dirtyFields: {},
    lastReconciliation: null,
    isSubmitted: false,

    updateFieldValue: (fieldId: string, value: FormFieldValue) => {
      set((state) => ({
        answers: {
          ...state.answers,
          [fieldId]: value,
        },
        dirtyFields: {
          ...state.dirtyFields,
          [fieldId]: true,
        },
        isSubmitted: false,
      }));
    },

    receiveNewSpec: (newSpec: DynamicFormSpec): ReconciliationOutcome => {
      const { answers, dirtyFields } = get();
      const outcome = reconcileAnswersWithSpec(answers, dirtyFields, newSpec);

      set({
        currentSpec: newSpec,
        answers: outcome.mergedAnswers,
        lastReconciliation: outcome,
        isSubmitted: false,
      });

      return outcome;
    },

    simulateAgentSpecRefresh: (): ReconciliationOutcome => {
      const current = get().currentSpec;
      const nextVersion = current.version + 1;

      const evolvedSpec: DynamicFormSpec = {
        ...current,
        version: nextVersion,
        pushedAt: new Date().toISOString(),
        description: `由 Agent 流式更新后的表单规格 (v${nextVersion})，已自适应追加风控约束`,
        fields: [
          ...current.fields.map((f) => {
            if (f.fieldId === 'cluster_name') {
              return {
                ...f,
                defaultValue: `k8s-edge-shanghai-${String(nextVersion).padStart(2, '0')}`,
              };
            }
            return f;
          }),
          {
            fieldId: `risk_mitigation_window_${nextVersion}`,
            label: `安全观测静默窗口 (v${nextVersion} 新增)`,
            type: 'number',
            defaultValue: 15,
            description: '每阶段步进放量后等待 Prometheus 评估的核心分钟数',
            required: true,
          },
          {
            fieldId: `notify_oncall_lead_${nextVersion}`,
            label: `抄送 Oncall 负责人 (v${nextVersion} 新增)`,
            type: 'boolean',
            defaultValue: true,
            description: '通过 Webhook 实时通知主值班团队群组',
          },
        ],
      };

      return get().receiveNewSpec(evolvedSpec);
    },

    submitForm: () => {
      set({ isSubmitted: true });
      return get().answers;
    },

    resetForm: () => {
      set({
        currentSpec: INITIAL_SPEC,
        answers: buildInitialAnswers(INITIAL_SPEC),
        dirtyFields: {},
        lastReconciliation: null,
        isSubmitted: false,
      });
    },
  })
);
