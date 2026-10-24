/** @vitest-environment jsdom */
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Agent } from '@/services/agent';
import { buildAgentConfig } from '@/lib/utils/agent-config';
import { useSkillStore } from '@/store/skill';
import useChatStore from '@/store/useChatStore';
import ChatWindow from '../ChatWindow';

const navigationMock = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  prefetch: vi.fn(),
  searchParams: new URLSearchParams(),
}));
const agentServiceMock = vi.hoisted(() => ({ getAgent: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: navigationMock.replace,
    push: navigationMock.push,
    prefetch: navigationMock.prefetch,
  }),
  useSearchParams: () => navigationMock.searchParams,
  usePathname: () => '/',
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/agent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/agent')>()),
  getAgent: agentServiceMock.getAgent,
}));

vi.mock('../Chat', () => ({ default: () => <div data-testid="chat" /> }));
vi.mock('../EmptyChat', () => ({ default: () => <textarea aria-label="message input" /> }));
vi.mock('../MessageListSkeleton', () => ({ default: () => <div>skeleton</div> }));
vi.mock('../ToolApprovalDialog', () => ({ default: () => null }));
vi.mock('../ToolApprovalExpiryWatcher', () => ({ default: () => null }));
vi.mock('../AgentInfoBanner', () => ({ default: () => null }));
vi.mock('../YoloModeBanner', () => ({ default: () => null }));
vi.mock('../EStopBanner', () => ({ default: () => null }));
vi.mock('../ExtensionDisconnectedBanner', () => ({ default: () => null }));
vi.mock('../ExtensionTakeoverBanner', () => ({ default: () => null }));
vi.mock('../ChatWindowSatellites', () => ({
  default: () => null,
  GoalControlPlane: () => null,
  GoalStatusCard: () => null,
  LifeStatusCapsule: () => null,
}));
vi.mock('../ParentChatLink', () => ({ ParentChatLink: () => null }));
vi.mock('../ChatCronLink', () => ({ ChatCronLink: () => null }));
vi.mock('../SubagentPromptButton', () => ({ default: () => null }));
vi.mock('../subagent/SubagentDashboard', () => ({ default: () => null }));
vi.mock('../artifacts/ArtifactPortal', () => ({ default: () => null }));
vi.mock('@/components/features/app-shell/VisualDesktopToggle', () => ({ VisualDesktopToggle: () => null }));
vi.mock('@/components/features/message-actions/SessionRevertButton', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/RunStatusChip', () => ({ default: () => null }));
vi.mock('@/components/features/copilot/SessionAdvisorPanel', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryBadge', () => ({ default: () => null }));
vi.mock('@/components/features/memory/pending/PendingMemoryDialog', () => ({ default: () => null }));

const SKILL_AUTHOR: Agent = {
  id: 'agent-skill-author',
  user_id: 'user-1',
  name: 'Skill Author',
  description: 'Writes reusable skills',
  system_prompt: 'You author skills.',
  skill_ids: [],
  mcp_ids: [],
  enabled_builtin_tools: ['skill_manage', 'web_search'],
  model_selection: { providerId: 'openai', model: 'gpt-4o' },
  engine_params: { temperature: 0.2 },
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
};

describe('ChatWindow agentId URL entry', () => {
  beforeEach(() => {
    navigationMock.replace.mockClear();
    navigationMock.searchParams = new URLSearchParams(`agentId=${SKILL_AUTHOR.id}`);
    agentServiceMock.getAgent.mockResolvedValue(SKILL_AUTHOR);
    useSkillStore.setState({
      fetchMarketSkills: vi.fn().mockResolvedValue(undefined),
      fetchLocalSkills: vi.fn().mockResolvedValue(undefined),
      marketSkills: [],
      localSkills: [],
    });
    useChatStore.setState({
      chatId: 'session-1',
      agentConfig: null,
      messages: [],
      isMessagesLoaded: true,
      loading: false,
      messageAppeared: false,
      notFound: false,
      loadError: false,
    });
  });

  it('applies the agent with the same mapping as session restore, keeping its builtin tools and model', async () => {
    render(<ChatWindow id="session-1" />);

    await waitFor(() => {
      expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id);
    });

    const applied = useChatStore.getState().agentConfig;
    expect(applied?.enabledBuiltinTools).toEqual(['skill_manage', 'web_search']);
    expect(applied?.modelSelection).toEqual({ providerId: 'openai', model: 'gpt-4o' });
    expect(applied?.engineParams).toEqual({ temperature: 0.2 });
    expect(applied).toMatchObject(buildAgentConfig(SKILL_AUTHOR));
    expect(navigationMock.replace).toHaveBeenCalledWith('/session-1', { scroll: false });
  });
});
