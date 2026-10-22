import { describe, it, expect, beforeEach } from 'vitest';
import { useProgressiveOnboardingStore, mapFailureToAttribution } from '../useProgressiveOnboardingStore';

describe('useProgressiveOnboardingStore & mapFailureToAttribution', () => {
  beforeEach(() => {
    useProgressiveOnboardingStore.getState().resetState();
  });

  it('initializes with first_chat_ready stage and default probes', () => {
    const state = useProgressiveOnboardingStore.getState();

    expect(state.stage).toBe('first_chat_ready');
    expect(state.activeTab).toBe('chat');
    expect(state.isFirstChatDispatched).toBe(false);
    expect(state.doctorProbes).toHaveLength(3);
    expect(state.failureAttribution).toBeNull();
  });

  it('dispatches first chat prompt without requiring API keys', () => {
    const store = useProgressiveOnboardingStore.getState();

    store.dispatchFirstChat('帮我快速分析这份财报数据');
    const updated = useProgressiveOnboardingStore.getState();

    expect(updated.isFirstChatDispatched).toBe(true);
    expect(updated.firstChatPrompt).toBe('帮我快速分析这份财报数据');
  });

  it('manages deferred configuration triggers and dismissal', () => {
    const store = useProgressiveOnboardingStore.getState();

    // 触发延迟配置
    store.triggerDeferredConfig('需要调度高级深度推理模型');
    expect(useProgressiveOnboardingStore.getState().stage).toBe('deferred_prompt_triggered');
    expect(useProgressiveOnboardingStore.getState().deferredReason).toBe('需要调度高级深度推理模型');

    // 稍后跳过
    store.dismissDeferredConfig();
    expect(useProgressiveOnboardingStore.getState().stage).toBe('first_chat_ready');

    // 完成配置
    store.completeConfiguration();
    expect(useProgressiveOnboardingStore.getState().stage).toBe('fully_configured');
  });

  it('correctly maps raw errors to key/address/room beginner analogies', () => {
    // 1. 钥匙类比 (Authentication / 401 / 403)
    const keyAttr = mapFailureToAttribution('AuthenticationError: 401 Unauthorized invalid_api_key');
    expect(keyAttr.category).toBe('key');
    expect(keyAttr.analogy).toContain('钥匙无效');
    expect(keyAttr.actionText).toContain('API Key');

    // 2. 地址/房间类比 (404 / Not Found)
    const urlAttr = mapFailureToAttribution('NotFoundError: 404 endpoint not found /v1/chat');
    expect(urlAttr.category).toBe('url_endpoint');
    expect(urlAttr.analogy).toContain('地址或房间号');
    expect(urlAttr.actionText).toContain('Base URL');

    // 3. 道路/网络类比 (Timeout / Connection Refused)
    const netAttr = mapFailureToAttribution('ConnectTimeout: Failed to establish a new connection: [Errno 60] Operation timed out');
    expect(netAttr.category).toBe('network');
    expect(netAttr.analogy).toContain('道路受阻');
    expect(netAttr.actionText).toContain('代理');

    // 4. 门票/配额类比 (429 / Rate Limit / Quota)
    const quotaAttr = mapFailureToAttribution('RateLimitError: 429 You exceeded your current quota');
    expect(quotaAttr.category).toBe('quota');
    expect(quotaAttr.analogy).toContain('门票点数已耗尽');
    expect(quotaAttr.actionText).toContain('充值');
  });

  it('stores and clears connection failure attribution in state', () => {
    const store = useProgressiveOnboardingStore.getState();

    store.analyzeConnectionFailure('Error: 401 Unauthorized');
    expect(useProgressiveOnboardingStore.getState().failureAttribution?.category).toBe('key');

    store.clearFailureAttribution();
    expect(useProgressiveOnboardingStore.getState().failureAttribution).toBeNull();
  });

  it('runs doctor probe self-healing on simulated warnings', () => {
    const store = useProgressiveOnboardingStore.getState();

    store.fixDoctorProbe('probe-sandbox-runtime');
    const fixedProbe = useProgressiveOnboardingStore.getState().doctorProbes.find((p) => p.id === 'probe-sandbox-runtime');

    expect(fixedProbe?.status).toBe('ok');
    expect(fixedProbe?.message).toContain('已自动完成自愈修复');
  });
});
