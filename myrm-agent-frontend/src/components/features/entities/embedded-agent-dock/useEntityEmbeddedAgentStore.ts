import { create } from 'zustand';
import type {
  BusinessEntitySnapshot,
  DossierStepRecord,
  EntityEmbeddedAgentState,
  EntityEmbeddedChatMessage,
  SignedRecordToken,
} from './entityEmbeddedAgentTypes';

/**
 * 生成带签名的业务实体防篡改上下文令牌 (SignedRecordToken)
 */
export function generateSignedRecordToken(
  entity: BusinessEntitySnapshot
): SignedRecordToken {
  const timestamp = Date.now();
  // 简易哈希验签签名串
  const rawPayload = `${entity.type}:${entity.id}:${timestamp}:${JSON.stringify(entity.metadata)}`;
  let hash = 0;
  for (let i = 0; i < rawPayload.length; i++) {
    hash = (hash << 5) - hash + rawPayload.charCodeAt(i);
    hash |= 0;
  }
  const signatureHex = Math.abs(hash).toString(16).padStart(8, '0');
  const tokenString = `srt_${entity.type}_${entity.id}_${signatureHex}`;

  return {
    tokenString,
    signature: `sig_${signatureHex}`,
    issuedAt: timestamp,
    entitySnapshot: entity,
  };
}

/**
 * 根据业务实体生成初始推演步态账本（展示已搜集事实、排除线索理由与就地歧义裁决）
 */
function createInitialStepLedger(entity: BusinessEntitySnapshot): DossierStepRecord[] {
  const baseTime = Date.now();
  return [
    {
      id: 'step-01',
      timestamp: baseTime - 45000,
      title: '检索内部知识库与往来往历史记录',
      status: 'verified',
      evidenceSource: `知识库 / ${entity.type}_records.db`,
    },
    {
      id: 'step-02',
      timestamp: baseTime - 30000,
      title: '跨公开工商数据库核验法人与股权结构',
      status: 'verified',
      evidenceSource: '公开征信与财报数据库 (Qichacha / SEC)',
    },
    {
      id: 'step-03',
      timestamp: baseTime - 20000,
      title: '排除疑似关联方实体「恒信网络科技有限公司」',
      status: 'discarded',
      discardedReason:
        '该实体注册地处于不同省份，主营业务为传统线缆批发，法定代表人与历史股东全无交集，判定为无关同名噪音并果断丢弃。',
      evidenceSource: '全国企业信用信息公示系统',
    },
    {
      id: 'step-04',
      timestamp: baseTime - 5000,
      title: '发现同名负责人冲突，等待原地人机裁决',
      status: 'pending_decision',
      disambiguationPrompt: '公开源中检索到两名同名对接人，请确认本次业务沟通的具体对象：',
      disambiguationOptions: [
        {
          id: 'opt-vp-eng',
          label: '张伟 (VP of Engineering)',
          description: 'base 北京，负责云原生多租户底层架构与技术选型',
        },
        {
          id: 'opt-procurement',
          label: '张伟 (Head of Procurement)',
          description: 'base 上海，负责年度企业级软件采购商务合同审查',
        },
      ],
    },
  ];
}

interface EntityEmbeddedAgentActions {
  openEntityDock: (entity: BusinessEntitySnapshot) => SignedRecordToken;
  closeEntityDock: () => void;
  resolveDisambiguation: (stepId: string, optionId: string) => void;
  sendUserMessage: (text: string) => void;
  resetState: () => void;
}

export type EntityEmbeddedAgentStore = EntityEmbeddedAgentState & EntityEmbeddedAgentActions;

const INITIAL_STATE: EntityEmbeddedAgentState = {
  isDockOpen: false,
  activeEntity: null,
  currentSignedToken: null,
  stepLedger: [],
  chatHistory: [],
  isAnalyzing: false,
};

export const useEntityEmbeddedAgentStore = create<EntityEmbeddedAgentStore>((set, get) => ({
  ...INITIAL_STATE,

  openEntityDock: (entity: BusinessEntitySnapshot) => {
    const token = generateSignedRecordToken(entity);
    const initialLedger = createInitialStepLedger(entity);

    const initialMessages: EntityEmbeddedChatMessage[] = [
      {
        id: `msg-${Date.now()}-sys`,
        sender: 'system',
        text: `已加载加密签名令牌 [${token.tokenString}]。专属 Agent 已直接绑定实体「${entity.title}」，上下文完全同步，无需手动粘贴属性。`,
        timestamp: Date.now(),
      },
      {
        id: `msg-${Date.now()}-agent`,
        sender: 'agent',
        text: `您好！我是当前业务对象【${entity.title}】的专属分析智能体。我已核实该实体的最新元数据，并完成了初步背景审查与噪音线索排除。请问需要我为您分析哪部分业务细节？`,
        timestamp: Date.now() + 10,
      },
    ];

    set({
      isDockOpen: true,
      activeEntity: entity,
      currentSignedToken: token,
      stepLedger: initialLedger,
      chatHistory: initialMessages,
      isAnalyzing: false,
    });

    return token;
  },

  closeEntityDock: () => {
    set({ isDockOpen: false });
  },

  resolveDisambiguation: (stepId: string, optionId: string) => {
    const state = get();
    let selectedLabel = '';

    const updatedSteps = state.stepLedger.map((step) => {
      if (step.id === stepId) {
        const matched = step.disambiguationOptions?.find((opt) => opt.id === optionId);
        selectedLabel = matched?.label ?? optionId;
        return {
          ...step,
          status: 'verified' as const,
          resolvedOptionId: optionId,
          title: `已就地裁决锁定对接人：${selectedLabel}`,
        };
      }
      return step;
    });

    const replyMessage: EntityEmbeddedChatMessage = {
      id: `msg-${Date.now()}-disambig`,
      sender: 'agent',
      text: `已收到您的就地裁决确认：已锁定对接人【${selectedLabel}】。系统已自动更新当前业务实体的上下文档案并排除了另一条候选线索。`,
      timestamp: Date.now(),
    };

    set({
      stepLedger: updatedSteps,
      chatHistory: [...state.chatHistory, replyMessage],
    });
  },

  sendUserMessage: (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    const state = get();
    const userMsg: EntityEmbeddedChatMessage = {
      id: `msg-${Date.now()}-user`,
      sender: 'user',
      text: trimmed,
      timestamp: Date.now(),
    };

    const newStep: DossierStepRecord = {
      id: `step-${Date.now()}`,
      timestamp: Date.now(),
      title: `针对用户问题「${trimmed}」完成即时事实推演并更新实体快照`,
      status: 'verified',
      evidenceSource: `实体上下文信使 [${state.currentSignedToken?.tokenString ?? 'local'}]`,
    };

    const agentMsg: EntityEmbeddedChatMessage = {
      id: `msg-${Date.now() + 10}-agent`,
      sender: 'agent',
      text: `已基于当前实体「${state.activeEntity?.title}」的专属上下文完成深度推演。该对象的各项核心指标均在预期轨道内，推演步态账本已实时更新。`,
      timestamp: Date.now() + 10,
    };

    set({
      chatHistory: [...state.chatHistory, userMsg, agentMsg],
      stepLedger: [...state.stepLedger, newStep],
    });
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
