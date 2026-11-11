/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - ../AgentIndicator (POS: 被测组件)
 *
 * [OUTPUT]
 * - kit: 替身句柄：语言、聊天状态、路由、提示、智能体详情读取、画廊数据
 * - resetIndicatorKit: 恢复为空画廊、无已选智能体的 agent 模式，并给 Radix 弹层补上 ResizeObserver
 * - renderIndicator / openMenu: 渲染指示器；用键盘打开真实的下拉菜单
 * - preset / customAgent / fullAgent: 画廊预设、自定义智能体列表项、智能体详情的样例构造器
 * - deferred: 手动控制完成时机的 Promise
 *
 * [POS]
 * AgentIndicator 行为测试的共享底座。必须先于 ../AgentIndicator 导入：vi.mock 在本模块求值时登记。
 * 下拉与提示用真实的 Radix 组件；状态总线、画廊 Hook、路由与提示换成替身；文案取真实语言包；
 * 图标解析只认识 Code 与 Search，每个名称对应一个稳定的占位组件，其余返回 null，与真实解析器一致。
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ComponentType } from 'react';
import { vi } from 'vitest';
import type { Agent, AgentListItem } from '@/services/agent';
import type { AgentConfig } from '@/store/chat/types/sessionConfig';
import type { PresetAgent } from '@/types/presetAgent';
import AgentIndicator from '../AgentIndicator';

const kit = vi.hoisted(() => ({
  locale: 'en' as 'en' | 'zh',
  chat: {
    agentConfig: null as AgentConfig | null,
    actionMode: 'agent' as string,
    loading: false,
    setAgentConfig: vi.fn<(config: AgentConfig) => void>(),
    toggleConfigPanel: vi.fn<() => void>(),
  },
  router: { push: vi.fn<(href: string) => void>() },
  toast: vi.fn<(options: { title: string; description?: string }) => void>(),
  fetchAgent: vi.fn<(agentId: string) => Promise<Agent | null>>(),
  gallery: { presets: [] as PresetAgent[], customAgents: [] as AgentListItem[] },
}));
export { kit };

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => kit.locale));
vi.mock('next/navigation', () => ({ useRouter: () => kit.router }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: kit.toast }));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof kit.chat) => unknown) => selector(kit.chat),
}));
vi.mock('@/store/useAgentStore', () => ({ default: { getState: () => ({ fetchAgent: kit.fetchAgent }) } }));
vi.mock('@/hooks/agent/useAgentGallery', () => ({
  useAgentGallery: ({
    onSelectPreset,
    onSelectCustomAgent,
  }: {
    onSelectPreset: (agent: PresetAgent) => void;
    onSelectCustomAgent: (agent: AgentListItem) => void;
  }) => ({
    presetAgents: kit.gallery.presets,
    customAgents: kit.gallery.customAgents,
    handlePresetClick: onSelectPreset,
    handleCustomAgentClick: onSelectCustomAgent,
  }),
}));
vi.mock('@/components/agent/lucide-icon-resolver', async (importOriginal) => {
  const known = ['Code', 'Search'];
  const icons = new Map<string, ComponentType<{ size?: number; className?: string }>>();
  return {
    ...(await importOriginal<typeof import('@/components/agent/lucide-icon-resolver')>()),
    findLucideIcon: (name: string) => {
      if (!known.includes(name)) {
        return null;
      }
      let icon = icons.get(name);
      if (icon === undefined) {
        icon = ({ className }) => <svg data-testid={`icon-${name}`} className={className} />;
        icons.set(name, icon);
      }
      return icon;
    },
  };
});

const TIMESTAMPS = { created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' };

export const preset = (overrides: Partial<PresetAgent> = {}): PresetAgent => ({
  id: 'coder',
  name: 'Coder',
  category: 'general',
  icon: 'Code',
  skillIds: ['code_edit'],
  systemPrompt: 'You are an expert coder.',
  ...overrides,
});

export const customAgent = (overrides: Partial<AgentListItem> = {}): AgentListItem => ({
  id: 'finance',
  name: 'Finance',
  ...TIMESTAMPS,
  ...overrides,
});

export const fullAgent = (overrides: Partial<Agent> = {}): Agent => ({
  id: 'finance',
  user_id: 'u1',
  name: 'Finance',
  ...TIMESTAMPS,
  ...overrides,
});

export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

export function resetIndicatorKit(): void {
  cleanup();
  vi.resetAllMocks();
  kit.locale = 'en';
  Object.assign(kit.chat, { agentConfig: null, actionMode: 'agent', loading: false });
  Object.assign(kit.gallery, { presets: [], customAgents: [] });
  kit.fetchAgent.mockResolvedValue(null);
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
}

export const renderIndicator = () => render(<AgentIndicator />);

export function openMenu(): HTMLElement {
  fireEvent.keyDown(screen.getByRole('button', { name: 'Switch Agent' }), { key: 'Enter' });
  return screen.getByRole('menu');
}
