import { create } from 'zustand';
import type {
  AttributionCategory,
  ConnectionFailureAttribution,
  DoctorProbeResult,
  OnboardingStage,
  OnboardingWorkspaceTab,
  ProgressiveOnboardingState,
} from './progressiveOnboardingTypes';

interface ProgressiveOnboardingActions {
  setStage: (stage: OnboardingStage) => void;
  setActiveTab: (tab: OnboardingWorkspaceTab) => void;
  dispatchFirstChat: (prompt?: string) => void;
  triggerDeferredConfig: (reason: string) => void;
  dismissDeferredConfig: () => void;
  completeConfiguration: () => void;
  analyzeConnectionFailure: (rawError: string) => ConnectionFailureAttribution;
  clearFailureAttribution: () => void;
  runDoctorScan: () => void;
  fixDoctorProbe: (probeId: string) => void;
  resetState: () => void;
}

export type ProgressiveOnboardingStore = ProgressiveOnboardingState & ProgressiveOnboardingActions;

const INITIAL_PROBES: DoctorProbeResult[] = [
  {
    id: 'probe-sandbox-runtime',
    name: '沙箱独立运行时',
    status: 'ok',
    message: '本地隔离容器环境运行正常，端口 5173 畅通',
  },
  {
    id: 'probe-local-ollama',
    name: '本地 Ollama 推理通道',
    status: 'ok',
    message: '自动嗅探到本地服务运行中 (Qwen2.5-Coder)',
  },
  {
    id: 'probe-port-connectivity',
    name: '云端网关连通性',
    status: 'ok',
    message: '延迟 42ms，双向 WebSocket 通信就绪',
  },
];

const INITIAL_STATE: ProgressiveOnboardingState = {
  stage: 'first_chat_ready',
  activeTab: 'chat',
  isFirstChatDispatched: false,
  firstChatPrompt: '帮我总结这段文字并提炼3个执行要点',
  deferredReason: undefined,
  failureAttribution: null,
  doctorProbes: INITIAL_PROBES,
  isDoctorScanning: false,
};

export const mapFailureToAttribution = (rawError: string): ConnectionFailureAttribution => {
  const lower = rawError.toLowerCase();

  // 1. 钥匙无效 (Key)
  if (
    lower.includes('401') ||
    lower.includes('403') ||
    lower.includes('authentication') ||
    lower.includes('unauthorized') ||
    lower.includes('invalid_api_key')
  ) {
    return {
      category: 'key',
      title: '认证鉴权失败',
      analogy: '钥匙无效或已过期',
      hint: 'API Key 类似于开门的钥匙。当前填写的密钥不正确、已被撤销或没有权限访问该模型。',
      rawError,
      actionText: '行动建议：请检查并重新粘贴提供商控制台生成的最新有效 API Key。',
    };
  }

  // 2. 地址/房间不存在 (URL / Endpoint)
  if (
    lower.includes('404') ||
    lower.includes('not found') ||
    lower.includes('invalid url') ||
    lower.includes('unknown endpoint')
  ) {
    return {
      category: 'url_endpoint',
      title: '服务地址不存在',
      analogy: '地址或房间号填错',
      hint: 'Base URL 是大楼地址，Endpoint 是具体房间号。服务商在此路径下没有对应的模型接口。',
      rawError,
      actionText: '行动建议：请核对 Base URL 是否缺失了 /v1 或多写了后缀路径。',
    };
  }

  // 3. 网络不通 (Network)
  if (
    lower.includes('timeout') ||
    lower.includes('connection refused') ||
    lower.includes('dns') ||
    lower.includes('econnrefused') ||
    lower.includes('network')
  ) {
    return {
      category: 'network',
      title: '网络通信超时',
      analogy: '通往该地址的道路受阻',
      hint: '客户端无法与远端模型服务器建立 TCP/TLS 连接，可能是本地代理、防火墙或外网中断所致。',
      rawError,
      actionText: '行动建议：检查本地代理设置或 VPN 配置，确认该域名可正常 ping 通。',
    };
  }

  // 4. 配额用尽 (Quota)
  if (
    lower.includes('429') ||
    lower.includes('rate limit') ||
    lower.includes('quota') ||
    lower.includes('insufficient_balance')
  ) {
    return {
      category: 'quota',
      title: '调用配额用尽',
      analogy: '门票点数已耗尽',
      hint: '该 API Key 对应账号的免费额度已过期或预充值余额不足，触发了并发速率或额度熔断。',
      rawError,
      actionText: '行动建议：前往提供商账户充值，或在设置中无缝切换至免费备用模型。',
    };
  }

  // 默认兜底
  return {
    category: 'unknown',
    title: '未知通信异常',
    analogy: '异常排查提醒',
    hint: '未能自动归类该底层异常，可能为临时性服务端波动。',
    rawError,
    actionText: '行动建议：稍后重试，或联系管理员获取支持。',
  };
};

export const useProgressiveOnboardingStore = create<ProgressiveOnboardingStore>((set, get) => ({
  ...INITIAL_STATE,

  setStage: (stage: OnboardingStage) => {
    set({ stage });
  },

  setActiveTab: (tab: OnboardingWorkspaceTab) => {
    set({ activeTab: tab });
  },

  dispatchFirstChat: (prompt?: string) => {
    set((state) => ({
      isFirstChatDispatched: true,
      firstChatPrompt: prompt ?? state.firstChatPrompt,
    }));
  },

  triggerDeferredConfig: (reason: string) => {
    set({
      stage: 'deferred_prompt_triggered',
      deferredReason: reason,
    });
  },

  dismissDeferredConfig: () => {
    set({
      stage: 'first_chat_ready',
      deferredReason: undefined,
    });
  },

  completeConfiguration: () => {
    set({
      stage: 'fully_configured',
      deferredReason: undefined,
    });
  },

  analyzeConnectionFailure: (rawError: string) => {
    const attribution = mapFailureToAttribution(rawError);
    set({ failureAttribution: attribution });
    return attribution;
  },

  clearFailureAttribution: () => {
    set({ failureAttribution: null });
  },

  runDoctorScan: () => {
    set({ isDoctorScanning: true });
    // 模拟轻量探针扫描
    setTimeout(() => {
      set({ isDoctorScanning: false });
    }, 100);
  },

  fixDoctorProbe: (probeId: string) => {
    set((state) => ({
      doctorProbes: state.doctorProbes.map((probe) => {
        if (probe.id === probeId) {
          return {
            ...probe,
            status: 'ok',
            message: `${probe.name} 已自动完成自愈修复，恢复正常`,
            fixActionText: undefined,
          };
        }
        return probe;
      }),
    }));
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
