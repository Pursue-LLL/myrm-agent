import { beforeEach, describe, expect, it } from 'vitest';
import { ConversationalConfigIntent } from '../conversationalConfigTypes';
import { useConversationalConfigStore } from '../useConversationalConfigStore';

describe('useConversationalConfigStore', () => {
  beforeEach(() => {
    useConversationalConfigStore.getState().reset();
  });

  it('initializes with default state', () => {
    const state = useConversationalConfigStore.getState();
    expect(state.activeConfigCards).toEqual({});
    expect(state.isNonDevWizardOpen).toBe(false);
    expect(state.wizardCurrentStep).toBe(1);
    expect(state.appliedConfigurations.model_name).toBe('claude-3-7-sonnet');
    expect(state.appliedConfigurations.search_engine).toBe('tavily');
  });

  it('triggers config intent successfully when utterance matches', () => {
    const cardId = useConversationalConfigStore
      .getState()
      .triggerConfigIntent('切换模型为 deepseek');
    expect(cardId).not.toBeNull();
    const store = useConversationalConfigStore.getState();
    const card = cardId ? store.activeConfigCards[cardId] : undefined;
    expect(card).toBeDefined();
    expect(card?.category).toBe('model_switch');
  });

  it('returns null and does not add card for unrelated utterance', () => {
    const cardId = useConversationalConfigStore
      .getState()
      .triggerConfigIntent('今天几号了');
    expect(cardId).toBeNull();
    expect(
      Object.keys(useConversationalConfigStore.getState().activeConfigCards)
        .length,
    ).toBe(0);
  });

  it('updates card param value', () => {
    const sampleCard: ConversationalConfigIntent = {
      id: 'test-card-1',
      category: 'api_key_entry',
      title: 'OpenAI 密钥配置',
      description: '输入 key',
      matchedUtterance: '配置 key',
      params: [
        {
          key: 'api_key',
          label: 'API Key',
          type: 'password',
          value: '',
          isSecret: true,
        },
      ],
      isApplied: false,
      createdAt: Date.now(),
    };

    useConversationalConfigStore.getState().addConfigCard(sampleCard);
    useConversationalConfigStore
      .getState()
      .updateCardParamValue('test-card-1', 'api_key', 'sk-new-token');

    const card =
      useConversationalConfigStore.getState().activeConfigCards['test-card-1'];
    expect(card?.params[0]?.value).toBe('sk-new-token');
  });

  it('validates before applying configuration', () => {
    const sampleCard: ConversationalConfigIntent = {
      id: 'test-card-secret',
      category: 'api_key_entry',
      title: '秘钥配置',
      description: '需要填 key',
      matchedUtterance: '填 key',
      params: [
        {
          key: 'api_key',
          label: 'API Key',
          type: 'password',
          value: '',
          isSecret: true,
        },
      ],
      isApplied: false,
      createdAt: Date.now(),
    };

    useConversationalConfigStore.getState().addConfigCard(sampleCard);
    const successEmpty = useConversationalConfigStore
      .getState()
      .applyConfiguration('test-card-secret');
    expect(successEmpty).toBe(false);

    useConversationalConfigStore
      .getState()
      .updateCardParamValue('test-card-secret', 'api_key', 'sk-valid-key');
    const successFilled = useConversationalConfigStore
      .getState()
      .applyConfiguration('test-card-secret');
    expect(successFilled).toBe(true);

    const updatedCard =
      useConversationalConfigStore.getState().activeConfigCards[
        'test-card-secret'
      ];
    expect(updatedCard?.isApplied).toBe(true);
    expect(
      useConversationalConfigStore.getState().appliedConfigurations['api_key'],
    ).toBe('sk-valid-key');

    // 再应用一次应返回 false
    const reapply = useConversationalConfigStore
      .getState()
      .applyConfiguration('test-card-secret');
    expect(reapply).toBe(false);
  });

  it('dismisses config card', () => {
    const sampleCard: ConversationalConfigIntent = {
      id: 'card-to-dismiss',
      category: 'search_engine',
      title: '搜索切换',
      description: '',
      matchedUtterance: '',
      params: [],
      isApplied: false,
      createdAt: Date.now(),
    };
    useConversationalConfigStore.getState().addConfigCard(sampleCard);
    expect(
      useConversationalConfigStore.getState().activeConfigCards[
        'card-to-dismiss'
      ],
    ).toBeDefined();

    useConversationalConfigStore.getState().dismissConfigCard('card-to-dismiss');
    expect(
      useConversationalConfigStore.getState().activeConfigCards[
        'card-to-dismiss'
      ],
    ).toBeUndefined();
  });

  it('controls wizard open state and step navigation within boundaries', () => {
    useConversationalConfigStore.getState().toggleNonDevWizard(true);
    expect(useConversationalConfigStore.getState().isNonDevWizardOpen).toBe(
      true,
    );

    useConversationalConfigStore.getState().setWizardStep(2);
    expect(useConversationalConfigStore.getState().wizardCurrentStep).toBe(2);

    // 边界 clamp 测试
    useConversationalConfigStore.getState().setWizardStep(99);
    expect(useConversationalConfigStore.getState().wizardCurrentStep).toBe(3);

    useConversationalConfigStore.getState().setWizardStep(-5);
    expect(useConversationalConfigStore.getState().wizardCurrentStep).toBe(1);

    useConversationalConfigStore.getState().toggleNonDevWizard();
    expect(useConversationalConfigStore.getState().isNonDevWizardOpen).toBe(
      false,
    );
  });
});
