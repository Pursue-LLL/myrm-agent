/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ExpertSummonPopover (POS: 输入框选项区的专家团队发现与召唤浮层)
 * - @/store/useChatStore::inputMessage (POS: 召唤后预填的输入框草稿，真实 store)
 *
 * [OUTPUT]
 * Vitest: 打开即拉取并上报曝光、加载/失败/空态、关闭后迟到的响应不覆盖新一轮、搜索过滤与埋点、
 * 召唤成功（提示、预填、关闭、跳转）与失败（可重试）、召唤中所有入口禁用。
 *
 * [POS]
 * 模板服务、埋点、提示与路由用替身，草稿预填与搜索匹配走真实实现。
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TemplateListItem } from '@/services/agentTemplates';
import useChatStore from '@/store/useChatStore';

const mocks = vi.hoisted(() => ({
  t: (key: string, params?: { name?: string }) => (params?.name ? `${key}:${params.name}` : key),
  getTemplates: vi.fn<() => Promise<TemplateListItem[]>>(),
  instantiate: vi.fn<(options: Record<string, unknown>) => Promise<{ id: string }>>(),
  surfaceViewed: vi.fn<(surface: string) => void>(),
  searchUsed: vi.fn<(surface: string, length: number) => void>(),
  toastSuccess: vi.fn<(message: string) => void>(),
  toastError: vi.fn<(message: string) => void>(),
  router: { push: vi.fn<(href: string) => void>() },
}));

vi.mock('next-intl', () => ({ useTranslations: () => mocks.t }));
vi.mock('next/navigation', () => ({ useRouter: () => mocks.router }));
vi.mock('sonner', () => ({ toast: { success: mocks.toastSuccess, error: mocks.toastError } }));
vi.mock('@/services/agentTemplates', () => ({ getTemplates: mocks.getTemplates }));
vi.mock('@/services/expertSummonMetrics', () => ({
  recordExpertSummonSurfaceViewed: mocks.surfaceViewed,
  recordExpertSummonSearchUsed: mocks.searchUsed,
}));
vi.mock('@/services/templateSummon', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/templateSummon')>()),
  instantiateTemplateWithMetrics: mocks.instantiate,
}));

import { ExpertSummonPopover } from '../ExpertSummonPopover';

const SQUAD: TemplateListItem = {
  id: 'team-arch',
  name: 'Architecture Squad',
  agent_type: 'team',
  description: 'Lead architects and reviewers',
  use_cases: ['Review system refactoring plan', 'Plan a migration', 'Audit the module boundaries'],
};
const TUNER: TemplateListItem = { id: 'agent-db', name: 'DB Tuning Expert', agent_type: 'individual' };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const menu = () => screen.getByTestId('expert-summon-popover-menu');
const summonButtons = () => screen.getAllByRole('button', { name: 'summonButton' });

async function openPopover() {
  await act(async () => {
    fireEvent.click(screen.getByTestId('expert-summon-popover-trigger'));
  });
}

async function closeFromHeader() {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'close' }));
  });
}

async function openWith(templates: TemplateListItem[], onSummoned?: (agentId: string) => void) {
  mocks.getTemplates.mockResolvedValue(templates);
  render(<ExpertSummonPopover onSummoned={onSummoned} />);
  await openPopover();
}

const search = (text: string) =>
  fireEvent.change(screen.getByPlaceholderText('searchPlaceholder'), { target: { value: text } });

describe('ExpertSummonPopover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({ inputMessage: '' });
    mocks.instantiate.mockResolvedValue({ id: 'agent-new' });
  });

  describe('loading the templates', () => {
    it('reports a view and asks for the templates every time it opens', async () => {
      await openWith([SQUAD]);
      expect(mocks.surfaceViewed).toHaveBeenCalledExactlyOnceWith('flow_pad_inline');
      expect(mocks.getTemplates).toHaveBeenCalledOnce();

      await closeFromHeader();
      expect(screen.queryByTestId('expert-summon-popover-menu')).toBeNull();
      await openPopover();

      expect(mocks.surfaceViewed).toHaveBeenCalledTimes(2);
      expect(mocks.getTemplates).toHaveBeenCalledTimes(2);
    });

    it('shows a loading state until the templates arrive', async () => {
      const pending = deferred<TemplateListItem[]>();
      mocks.getTemplates.mockReturnValue(pending.promise);
      render(<ExpertSummonPopover />);
      await openPopover();

      expect(within(menu()).getByText('loading')).toBeInTheDocument();
      expect(screen.queryByText('empty')).toBeNull();

      await act(async () => pending.resolve([SQUAD]));

      expect(screen.queryByText('loading')).toBeNull();
      expect(screen.getByText('Architecture Squad')).toBeInTheDocument();
    });

    it('shows the empty state when the templates cannot be loaded', async () => {
      mocks.getTemplates.mockRejectedValue(new Error('offline'));
      render(<ExpertSummonPopover />);
      await openPopover();

      expect(await screen.findByText('empty')).toBeInTheDocument();
      expect(screen.queryByText('loading')).toBeNull();
    });

    it.each([
      ['an answer', (late: ReturnType<typeof deferred<TemplateListItem[]>>) => late.resolve([SQUAD])],
      ['a failure', (late: ReturnType<typeof deferred<TemplateListItem[]>>) => late.reject(new Error('late'))],
    ])('ignores %s that reaches a popover which was closed and reopened since', async (_label, settle) => {
      const abandoned = deferred<TemplateListItem[]>();
      const current = deferred<TemplateListItem[]>();
      mocks.getTemplates.mockReturnValueOnce(abandoned.promise).mockReturnValueOnce(current.promise);
      render(<ExpertSummonPopover />);
      await openPopover();
      await closeFromHeader();
      await openPopover();

      await act(async () => settle(abandoned));

      expect(screen.getByText('loading')).toBeInTheDocument();
      expect(screen.queryByText('Architecture Squad')).toBeNull();
      expect(screen.queryByText('empty')).toBeNull();

      await act(async () => current.resolve([TUNER]));

      expect(screen.getByText('DB Tuning Expert')).toBeInTheDocument();
      expect(screen.queryByText('Architecture Squad')).toBeNull();
    });
  });

  describe('listing and searching', () => {
    it('tells teams from individual experts and shows only what a template has', async () => {
      await openWith([SQUAD, TUNER]);

      expect(within(menu()).getAllByText('teamBadge')).toHaveLength(1);
      expect(within(menu()).getAllByText('expertBadge')).toHaveLength(1);
      expect(screen.getByText('Lead architects and reviewers')).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /^(Review|Plan|Audit)/ })).toHaveLength(2);
    });

    it('offers at most the first two use cases of a template', async () => {
      await openWith([SQUAD]);

      expect(screen.getByText('Review system refactoring plan')).toBeInTheDocument();
      expect(screen.getByText('Plan a migration')).toBeInTheDocument();
      expect(screen.queryByText('Audit the module boundaries')).toBeNull();
    });

    it('filters by the search text and reports each non-blank search with its length', async () => {
      await openWith([SQUAD, TUNER]);

      search('db');
      expect(screen.queryByText('Architecture Squad')).toBeNull();
      expect(screen.getByText('DB Tuning Expert')).toBeInTheDocument();
      expect(mocks.searchUsed).toHaveBeenCalledExactlyOnceWith('flow_pad_inline', 2);

      search('   ');
      expect(screen.getByText('Architecture Squad')).toBeInTheDocument();
      expect(screen.getByText('DB Tuning Expert')).toBeInTheDocument();
      expect(mocks.searchUsed).toHaveBeenCalledOnce();
    });

    it('says so when nothing matches the search', async () => {
      await openWith([SQUAD, TUNER]);

      search('zzz-no-such-expert');

      expect(screen.getByText('empty')).toBeInTheDocument();
      expect(screen.queryByText('Architecture Squad')).toBeNull();
    });
  });

  describe('summoning', () => {
    it('summons from the card: notes it, prefills the first use case, closes, and opens the new chat', async () => {
      const onSummoned = vi.fn<(agentId: string) => void>();
      await openWith([SQUAD, TUNER], onSummoned);

      await act(async () => {
        fireEvent.click(summonButtons()[0]);
      });

      expect(mocks.instantiate).toHaveBeenCalledExactlyOnceWith(
        expect.objectContaining({
          templateId: 'team-arch',
          surface: 'flow_pad_inline',
          trigger: 'template_card',
          fromSearch: false,
          usedUseCase: false,
        }),
      );
      expect(mocks.toastSuccess).toHaveBeenCalledExactlyOnceWith('summonSuccess:Architecture Squad');
      expect(useChatStore.getState().inputMessage).toBe('Review system refactoring plan');
      expect(screen.queryByTestId('expert-summon-popover-menu')).toBeNull();
      expect(onSummoned).toHaveBeenCalledExactlyOnceWith('agent-new');
      expect(mocks.router.push).toHaveBeenCalledExactlyOnceWith('/chat?agentId=agent-new');
    });

    it('summons through a use case after a search, and prefills that very use case', async () => {
      await openWith([SQUAD, TUNER]);
      search('architecture');

      await act(async () => {
        fireEvent.click(screen.getByText('Plan a migration'));
      });

      expect(mocks.instantiate).toHaveBeenCalledExactlyOnceWith(
        expect.objectContaining({
          templateId: 'team-arch',
          trigger: 'use_case_chip',
          fromSearch: true,
          usedUseCase: true,
        }),
      );
      expect(useChatStore.getState().inputMessage).toBe('Plan a migration');
    });

    it('summons a template without use cases and leaves the draft empty', async () => {
      await openWith([TUNER]);

      await act(async () => {
        fireEvent.click(summonButtons()[0]);
      });

      expect(mocks.router.push).toHaveBeenCalledExactlyOnceWith('/chat?agentId=agent-new');
      expect(useChatStore.getState().inputMessage).toBe('');
    });

    it.each([
      ['the reason the server gave', new Error('Agent quota exceeded'), 'Agent quota exceeded'],
      ['the generic message when there is no usable reason', new Error('  '), 'summonFailed'],
    ])('reports %s and lets the viewer try again', async (_label, failure, shown) => {
      mocks.instantiate.mockRejectedValueOnce(failure);
      await openWith([SQUAD]);

      await act(async () => {
        fireEvent.click(summonButtons()[0]);
      });

      expect(mocks.toastError).toHaveBeenCalledExactlyOnceWith(shown);
      expect(mocks.toastSuccess).not.toHaveBeenCalled();
      expect(mocks.router.push).not.toHaveBeenCalled();
      expect(useChatStore.getState().inputMessage).toBe('');
      expect(menu()).toBeInTheDocument();
      expect(summonButtons()[0]).toBeEnabled();

      await act(async () => {
        fireEvent.click(summonButtons()[0]);
      });
      expect(mocks.router.push).toHaveBeenCalledExactlyOnceWith('/chat?agentId=agent-new');
    });

    it('lets only one summon run at a time', async () => {
      const inFlight = deferred<{ id: string }>();
      mocks.instantiate.mockReturnValueOnce(inFlight.promise);
      await openWith([SQUAD, TUNER]);

      await act(async () => {
        fireEvent.click(summonButtons()[0]);
      });

      for (const button of [...summonButtons(), screen.getByText('Plan a migration').closest('button')]) {
        expect(button).toBeDisabled();
      }
      fireEvent.click(summonButtons()[1]);
      expect(mocks.instantiate).toHaveBeenCalledOnce();

      await act(async () => inFlight.resolve({ id: 'agent-new' }));
      expect(mocks.router.push).toHaveBeenCalledExactlyOnceWith('/chat?agentId=agent-new');
    });
  });

  it('closes from the button in its header', async () => {
    await openWith([SQUAD]);

    await closeFromHeader();

    expect(screen.queryByTestId('expert-summon-popover-menu')).toBeNull();
  });
});
