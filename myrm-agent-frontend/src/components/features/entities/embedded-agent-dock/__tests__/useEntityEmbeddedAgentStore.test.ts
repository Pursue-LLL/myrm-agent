import { describe, it, expect, beforeEach } from 'vitest';
import {
  useEntityEmbeddedAgentStore,
  generateSignedRecordToken,
} from '../useEntityEmbeddedAgentStore';
import type { BusinessEntitySnapshot } from '../entityEmbeddedAgentTypes';

describe('useEntityEmbeddedAgentStore & SignedRecordToken', () => {
  beforeEach(() => {
    useEntityEmbeddedAgentStore.getState().resetState();
  });

  const mockCompany: BusinessEntitySnapshot = {
    id: 'ent-comp-001',
    type: 'company',
    title: '字节跃动科技有限公司',
    subtitle: '企业协同 SaaS 业务部',
    metadata: {
      registeredCapital: '5000万人民币',
      industry: '云计算与企业级软件',
      employees: 3200,
    },
  };

  describe('generateSignedRecordToken', () => {
    it('generates a tamper-evident signed token with entity snapshot', () => {
      const token = generateSignedRecordToken(mockCompany);

      expect(token.tokenString).toContain('srt_company_ent-comp-001_');
      expect(token.signature).toContain('sig_');
      expect(token.entitySnapshot.title).toBe('字节跃动科技有限公司');
      expect(token.issuedAt).toBeGreaterThan(0);
    });
  });

  describe('openEntityDock and step dossier initialization', () => {
    it('opens dock, builds signed token and initializes step ledger with discarded leads', () => {
      const store = useEntityEmbeddedAgentStore.getState();
      const token = store.openEntityDock(mockCompany);

      const state = useEntityEmbeddedAgentStore.getState();
      expect(state.isDockOpen).toBe(true);
      expect(state.activeEntity?.title).toBe('字节跃动科技有限公司');
      expect(state.currentSignedToken).toEqual(token);

      // 验证步态账本：包含事实核实、线索排除与待决仲裁
      expect(state.stepLedger.length).toBeGreaterThanOrEqual(4);

      const verifiedStep = state.stepLedger.find((s) => s.status === 'verified');
      expect(verifiedStep).toBeDefined();

      const discardedStep = state.stepLedger.find((s) => s.status === 'discarded');
      expect(discardedStep).toBeDefined();
      expect(discardedStep?.discardedReason).toContain('无关同名噪音');

      const decisionStep = state.stepLedger.find((s) => s.status === 'pending_decision');
      expect(decisionStep).toBeDefined();
      expect(decisionStep?.disambiguationOptions).toHaveLength(2);

      // 验证初始系统信使与 Agent 开场白
      expect(state.chatHistory.length).toBe(2);
      expect(state.chatHistory[0]?.sender).toBe('system');
    });
  });

  describe('in-place disambiguation arbitration', () => {
    it('resolves disambiguation and updates step status to verified', () => {
      const store = useEntityEmbeddedAgentStore.getState();
      store.openEntityDock(mockCompany);

      const stepId = 'step-04';
      store.resolveDisambiguation(stepId, 'opt-vp-eng');

      const state = useEntityEmbeddedAgentStore.getState();
      const updatedStep = state.stepLedger.find((s) => s.id === stepId);

      expect(updatedStep?.status).toBe('verified');
      expect(updatedStep?.resolvedOptionId).toBe('opt-vp-eng');
      expect(updatedStep?.title).toContain('张伟 (VP of Engineering)');

      // 会话流自动追加确认说明
      const lastMsg = state.chatHistory[state.chatHistory.length - 1];
      expect(lastMsg?.sender).toBe('agent');
      expect(lastMsg?.text).toContain('就地裁决确认');
    });
  });

  describe('chat interaction with entity context', () => {
    it('sends user message and appends response with step ledger update', () => {
      const store = useEntityEmbeddedAgentStore.getState();
      store.openEntityDock(mockCompany);

      store.sendUserMessage('该公司的采购审批周期通常是多久？');

      const state = useEntityEmbeddedAgentStore.getState();
      const userMsg = state.chatHistory.find(
        (m) => m.text === '该公司的采购审批周期通常是多久？'
      );
      expect(userMsg).toBeDefined();
      expect(userMsg?.sender).toBe('user');

      // 验证步态账本新增推演记录
      const newStep = state.stepLedger.find((s) =>
        s.title.includes('该公司的采购审批周期通常是多久？')
      );
      expect(newStep).toBeDefined();
      expect(newStep?.status).toBe('verified');
    });

    it('ignores empty message input', () => {
      const store = useEntityEmbeddedAgentStore.getState();
      store.openEntityDock(mockCompany);
      const initialCount = useEntityEmbeddedAgentStore.getState().chatHistory.length;

      store.sendUserMessage('   ');
      expect(useEntityEmbeddedAgentStore.getState().chatHistory.length).toBe(initialCount);
    });
  });

  describe('close and reset', () => {
    it('closes dock and resets state cleanly', () => {
      const store = useEntityEmbeddedAgentStore.getState();
      store.openEntityDock(mockCompany);
      expect(useEntityEmbeddedAgentStore.getState().isDockOpen).toBe(true);

      store.closeEntityDock();
      expect(useEntityEmbeddedAgentStore.getState().isDockOpen).toBe(false);

      store.resetState();
      expect(useEntityEmbeddedAgentStore.getState().activeEntity).toBeNull();
      expect(useEntityEmbeddedAgentStore.getState().stepLedger).toHaveLength(0);
    });
  });
});
