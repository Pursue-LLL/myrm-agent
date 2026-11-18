/**
 * [INPUT]
 * - vitest::vi (POS: 全局替身登记：ResizeObserver 与被拒绝的浏览器存储)
 * - @/store/useProviderStore (POS: 真实的 Provider store，用来配置默认模型及其上报的推理能力)
 * - ../ThinkingIntensityButton (POS: 被测组件及其全局选择读写口)
 *
 * [OUTPUT]
 * - REASONING_MODEL / PLAIN_MODEL: 仅凭名字就被认作推理模型的名字 / 认不出推理能力的名字
 * - configureModel: 设置默认主模型（null 为未配置），可附带该模型上报的推理能力
 * - renderButton: 以 agent 模式渲染按钮
 * - openPopover / openCustomField: 打开弹层 / 再展开自定义输入框并返回它
 * - blockStorage: 让浏览器存储的每次访问都抛错
 * - resetThinkingIntensityKit: 每个用例前的归位：补上 ResizeObserver、清空存储、选择回到自动、默认模型为推理模型
 *
 * [POS]
 * ThinkingIntensityButton 界面测试的共享底座。各测试文件自己登记 next-intl 的真实英文文案；
 * 选择的保存与恢复、弹层与输入框都是真实的，只有提示箭头用到的 ResizeObserver 和被拒绝的浏览器存储是替身。
 */
import { render, screen, within } from '@testing-library/react';
import type userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { getInitialDefaultModelConfig, type CustomModelInfo } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';
import ThinkingIntensityButton, { setGlobalIntensity } from '../ThinkingIntensityButton';

/** Recognised as a reasoning model by name alone. */
export const REASONING_MODEL = 'o3-mini';
export const PLAIN_MODEL = 'gpt-4o';

export function configureModel(model: string | null, supportsReasoning?: boolean) {
  const info: CustomModelInfo = {
    source: 'user',
    lastUpdated: '2026-01-01T00:00:00Z',
    supports_reasoning: supportsReasoning,
  };
  useProviderStore.setState({
    providers: [],
    customModelInfo: model && supportsReasoning !== undefined ? { [`acme/${model}`]: info } : {},
    defaultModelConfig: {
      ...getInitialDefaultModelConfig(),
      baseModel: { primary: model ? { providerId: 'acme', model } : null, fallback: null },
    },
  });
}

export function renderButton() {
  return render(<ThinkingIntensityButton actionMode="agent" agentConfig={null} />);
}

export async function openPopover(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /^Thinking Intensity/ }));
  return screen.findByRole('dialog');
}

export async function openCustomField(user: ReturnType<typeof userEvent.setup>) {
  const dialog = await openPopover(user);
  await user.click(within(dialog).getByRole('button', { name: 'Custom' }));
  return screen.getByRole('textbox', { name: 'Custom' });
}

/** Storage the browser refuses to hand out: every access throws. */
export function blockStorage() {
  const refuse = () => {
    throw new DOMException('blocked', 'SecurityError');
  };
  vi.stubGlobal('localStorage', { getItem: refuse, setItem: refuse, removeItem: refuse });
}

/** Back to the state every case starts from: auto intensity, nothing saved, a model recognised as a reasoning one. */
export function resetThinkingIntensityKit() {
  // The tooltip arrow measures itself.
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  localStorage.clear();
  setGlobalIntensity('auto');
  configureModel(REASONING_MODEL);
}
