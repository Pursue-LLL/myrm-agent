import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WechatArticleComposerHint } from '../WechatArticleComposerHint';

interface SkillStub {
  id: string;
  name: string;
}

const chatState = vi.hoisted(() => ({
  agentConfig: null as { agentId: string; selectedSkillIds: string[] } | null,
  sessionSkillOverrides: null as string[] | null,
}));
const skillState = vi.hoisted(() => ({
  marketSkills: [] as SkillStub[],
  localSkills: [] as SkillStub[],
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof chatState) => unknown) => selector(chatState),
}));
vi.mock('@/store/skill/useSkillStore', () => ({
  default: (selector: (state: typeof skillState) => unknown) => selector(skillState),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const ARTICLE = 'summarise https://mp.weixin.qq.com/s/abc';
const FORMATTER: SkillStub = { id: 'formatter-1', name: 'wechat-article-formatter' };

function mountFormatter(where: 'marketSkills' | 'localSkills' = 'localSkills') {
  skillState[where] = [FORMATTER];
  chatState.agentConfig = { agentId: 'agent-7', selectedSkillIds: [FORMATTER.id] };
}

beforeEach(() => {
  chatState.agentConfig = { agentId: 'agent-7', selectedSkillIds: [] };
  chatState.sessionSkillOverrides = null;
  skillState.marketSkills = [];
  skillState.localSkills = [];
});

describe('WechatArticleComposerHint', () => {
  it('shows nothing until the text holds a WeChat article link', () => {
    const { container, rerender } = render(<WechatArticleComposerHint inputMessage="just words" />);
    expect(container).toBeEmptyDOMElement();

    rerender(<WechatArticleComposerHint inputMessage={ARTICLE} />);

    expect(screen.getByTestId('wechat-article-composer-hint')).toBeInTheDocument();
  });

  it('points to the agent skill settings while the formatter is not mounted', () => {
    render(<WechatArticleComposerHint inputMessage={ARTICLE} />);

    expect(screen.getByText('WeChat article link detected')).toBeInTheDocument();
    expect(screen.getByText(/^Mount the WeChat Article Formatter skill/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open agent skills' })).toHaveAttribute(
      'href',
      '/settings/agents?agentId=agent-7#loadout',
    );
  });

  it('falls back to the general agent settings when no agent is loaded', () => {
    chatState.agentConfig = null;

    render(<WechatArticleComposerHint inputMessage={ARTICLE} />);

    expect(screen.getByRole('link', { name: 'Open agent skills' })).toHaveAttribute('href', '/settings/agents#loadout');
  });

  it.each(['localSkills', 'marketSkills'] as const)(
    'says it is ready once the formatter from %s is mounted',
    (where) => {
      mountFormatter(where);

      render(<WechatArticleComposerHint inputMessage={ARTICLE} />);

      expect(screen.getByText('WeChat formatter skill is ready')).toBeInTheDocument();
      expect(screen.getByText(/^After the agent finishes/)).toBeInTheDocument();
      expect(screen.queryByRole('link')).toBeNull();
    },
  );

  it('asks to mount it when the formatter is installed but this agent does not use it', () => {
    skillState.localSkills = [FORMATTER];

    render(<WechatArticleComposerHint inputMessage={ARTICLE} />);

    expect(screen.getByRole('link', { name: 'Open agent skills' })).toBeInTheDocument();
  });

  it('asks again when this session switched the formatter off', () => {
    mountFormatter();
    chatState.sessionSkillOverrides = ['some-other-skill'];

    render(<WechatArticleComposerHint inputMessage={ARTICLE} />);

    expect(screen.getByText('WeChat article link detected')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open agent skills' })).toBeInTheDocument();
  });

  it('stays ready when the session override keeps the formatter', () => {
    mountFormatter();
    chatState.sessionSkillOverrides = ['wechat-article-formatter'];

    render(<WechatArticleComposerHint inputMessage={ARTICLE} />);

    expect(screen.getByText('WeChat formatter skill is ready')).toBeInTheDocument();
  });

  it('goes away when dismissed and stays away while the component lives', () => {
    const { rerender } = render(<WechatArticleComposerHint inputMessage={ARTICLE} />);

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByTestId('wechat-article-composer-hint')).toBeNull();

    rerender(<WechatArticleComposerHint inputMessage="another https://mp.weixin.qq.com/s?__biz=x" />);
    expect(screen.queryByTestId('wechat-article-composer-hint')).toBeNull();
  });

  it('lets the parent add classes without losing its own', () => {
    render(<WechatArticleComposerHint inputMessage={ARTICLE} className="extra-class" />);

    const hint = screen.getByTestId('wechat-article-composer-hint');
    expect(hint).toHaveClass('extra-class');
    expect(hint).toHaveClass('border');
  });
});
