/** @vitest-environment jsdom */
/**
 * MarkdownContent 的元素映射（code / a / img / table / citation / vault / 思考标签）。
 *
 * 子组件换成会把收到的 props 摊成 data-* 属性的桩，把「哪个元素交给了哪个组件、传了哪些参数」
 * 固定成可读的 HTML 快照；以后改动这张映射表时，靠这份快照证明行为没变。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { Artifact, Source } from '@/store/chat/types';

type StubTag = 'div' | 'span' | 'pre' | 'button' | 'i';

/** 桩组件收到的 props 摊成 data-* 属性：函数与 react-markdown 注入的 hast `node` 不进快照，其余对象按 JSON 展开。 */
function dataAttributes(props: Record<string, unknown>): Record<string, string> {
  const attributes: Record<string, string> = {};
  for (const [name, value] of Object.entries(props)) {
    if (name === 'node' || value === undefined || value === null || typeof value === 'function') {
      continue;
    }
    const attribute = `data-${name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
    attributes[attribute] = typeof value === 'object' ? JSON.stringify(value) : String(value);
  }
  return attributes;
}

/** 生成桩组件：`contentProp` 指向的 prop 渲染成文本内容，其余 props 摊成 data-* 属性。 */
function stub(mock: string, tag: StubTag = 'div', contentProp = 'children') {
  return function Stub(props: Record<string, unknown>) {
    const { [contentProp]: content, ...attributes } = props;
    return createElement(tag, { 'data-mock': mock, ...dataAttributes(attributes) }, content as ReactNode);
  };
}

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/hooks/message-input/useSmoothStream', () => ({
  useSmoothStream: () => ({ addChunk: vi.fn(), displayedContent: '', flush: vi.fn(), reset: vi.fn() }),
}));
vi.mock('@/store/useConfigStore', () => ({ default: () => false }));
vi.mock('@/services/wiki/evidenceMetrics', () => ({ recordEvidenceSurface: vi.fn() }));
vi.mock('@/services/wikiService', () => ({
  buildWikiAssetUrl: (filename: string, agentId?: string) => `asset://${agentId ?? ''}/${filename}`,
}));

vi.mock('@/components/features/markdown-render-tools/LinkPopover', () => ({
  default: stub('link-popover', 'span', 'label'),
}));
vi.mock('@/components/features/markdown-render-tools/CodeBlock', () => ({
  default: stub('code-block', 'pre', 'value'),
}));
vi.mock('@/components/features/markdown-render-tools/InlineHtmlWidget', () => ({
  default: stub('inline-html', 'div', 'value'),
}));
vi.mock('@/components/features/markdown-render-tools/MermaidChart', () => ({
  default: stub('mermaid', 'div', 'chart'),
}));
vi.mock('@/components/features/markdown-render-tools/InlineDiffViewer', () => ({
  default: stub('diff', 'pre', 'diff'),
}));
vi.mock('@/components/features/markdown-render-tools/MarkdownImage', () => ({ default: stub('image', 'i') }));
vi.mock('@/components/features/markdown-render-tools/ResponsiveTable', () => ({ default: stub('table') }));
vi.mock('@/components/features/markdown-render-tools/ThinkTagProcessor', () => ({ default: stub('think') }));
vi.mock('@/components/features/artifacts/VaultArtifactCard', () => ({ default: stub('vault') }));
vi.mock('@/components/features/embeds', () => ({
  detectEmbed: (href: string) => (href.includes('youtube.com') ? { provider: 'youtube', href } : null),
  UrlEmbed: stub('embed'),
}));
vi.mock('@/components/features/embeds/OgCard', () => ({ OgCard: stub('og-card') }));
vi.mock('../DeliverableReferenceLink', () => ({ default: stub('deliverable', 'button', 'label') }));
vi.mock('../SourceChunkDrawer', () => ({ default: stub('kb-drawer') }));

import MarkdownContent from '../MarkdownContent';

/**
 * 正文容器的内部 HTML：去掉外层一长串 class、抽屉桩与块之间只含换行的文本节点，
 * 再在每个标签边界换行，快照才看得清。
 */
function bodyMarkup(container: HTMLElement): string {
  const body = container.firstElementChild?.cloneNode(true) as HTMLElement;
  body.querySelector('[data-mock="kb-drawer"]')?.remove();
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  const blockSeparators: Node[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (/^\s*\n\s*$/.test(node.nodeValue ?? '')) {
      blockSeparators.push(node);
    }
  }
  blockSeparators.forEach((node) => node.parentNode?.removeChild(node));
  return body.innerHTML.replace(/></g, '>\n<');
}

const ARTIFACTS = [{ id: 'file-1', filename: 'q1-summary.md' }] as Artifact[];

function renderContent(content: string, options: { isStreaming?: boolean; sources?: Source[] } = {}) {
  return render(
    <MarkdownContent
      content={content}
      sources={options.sources ?? []}
      messageId="msg-characterization"
      isStreaming={options.isStreaming ?? false}
      chatId="chat-1"
      workspaceDir="/work/space"
      messageArtifacts={ARTIFACTS}
    />,
  );
}

function renderBody(content: string, options: { isStreaming?: boolean; sources?: Source[] } = {}): string {
  return bodyMarkup(renderContent(content, options).container);
}

const FENCES = [
  '```ts\nconst answer = 42;\n```',
  '```mermaid\ngraph TD; A-->B\n```',
  '```diff\n-old\n+new\n```',
  '```html\n<b>widget</b>\n```',
  '```\nplain fence\nsecond line\n```',
].join('\n\n');

const STREAMING_FENCES = ['```ts\nconst answer = 42;\n```', '```html\n<b>widget</b>\n```'].join('\n\n');

const INLINE_CODE = ['`workspace/reports/q1-summary.md`', '`artifact:abc123`', '`npm run build`'].join('\n\n');

const LINKS = [
  '[docs](https://example.com/docs)',
  'https://example.com/page',
  '[video](https://www.youtube.com/watch?v=abc)',
  '[top](#top) and [mail](mailto:hi@example.com)',
].join('\n\n');

const CARD_LINKS = ['https://example.com/page', '[video](https://www.youtube.com/watch?v=abc)'].join('\n\n');

const TABLE = '| h1 | h2 |\n| -- | -- |\n| a | b |';

const SOURCES: Source[] = [
  {
    index: 1,
    type: 'web_search',
    url: 'https://example.com/a',
    title: 'Web title',
    summary: 'Web summary',
    snippet: 'Web snippet',
    site_name: 'Example',
    authority_description: 'Official',
    date: '2026-01-02',
  },
  {
    index: 2,
    type: 'mcp',
    skill_name: 'Git skill',
    calls: [
      { tool_name: 'git_log', result_preview: 'abc123' },
      { tool_name: 'git_diff', result_preview: '' },
    ],
  },
  {
    index: 3,
    type: 'knowledge',
    kb_name: 'LLM-Wiki',
    filename: 'budget.md',
    section: 'index_routing',
    snippet: 'KB snippet',
    level: 'L2',
    snapshot_status: 'stale',
    claim_status: 'contested',
    claim_confidence: 0.5,
    claim_text: 'Claim text',
    resource_uri: 'raw/budget.md@sha',
    superseded_from_uri: 'raw/old.md',
    hit_kind: 'asset',
    asset_filename: 'chart.png',
    agent_id: 'agent-1',
  },
  { index: 4, type: 'knowledge', kb_name: 'LLM-Wiki', filename: 'empty.md' },
  { index: 5, type: 'conversation_history', title: 'Earlier chat', snippet: 'Earlier snippet' },
  { index: 6, type: 'web_fetch', url: '', title: 'No URL' },
];

const CITATIONS = [
  ...SOURCES.map(
    (source, position) =>
      `<citation data-source-index="${position}" data-num="${source.index}" data-url="${source.url ?? ''}"></citation>`,
  ),
  '<citation data-source-index="9" data-num="9"></citation>',
  '<citation data-source-index="x" data-num="x"></citation>',
].join(' ');

describe('MarkdownContent element mapping', () => {
  it('maps fenced code by language', () => {
    expect(renderBody(FENCES)).toMatchInlineSnapshot(`
      "<pre>
      <pre data-mock="code-block" data-language="ts" data-is-streaming="false">const answer = 42;</pre>
      </pre>
      <pre>
      <div data-mock="mermaid">graph TD; A--&gt;B</div>
      </pre>
      <pre>
      <pre data-mock="diff">-old
      +new</pre>
      </pre>
      <pre>
      <div data-mock="inline-html" data-language="html">&lt;b&gt;widget&lt;/b&gt;</div>
      </pre>
      <pre>
      <span>plain fence
      second line</span>
      </pre>"
    `);
  });

  it('keeps html fences as plain code blocks while streaming', () => {
    expect(renderBody(STREAMING_FENCES, { isStreaming: true })).toMatchInlineSnapshot(`
      "<pre>
      <pre data-mock="code-block" data-language="ts" data-is-streaming="true">const answer = 42;</pre>
      </pre>
      <pre>
      <pre data-mock="code-block" data-language="html" data-is-streaming="true">&lt;b&gt;widget&lt;/b&gt;</pre>
      </pre>"
    `);
  });

  it('turns inline code into a chip or a deliverable link', () => {
    expect(renderBody(INLINE_CODE)).toMatchInlineSnapshot(`
      "<p>
      <button data-mock="deliverable" data-reference="{&quot;kind&quot;:&quot;workspace&quot;,&quot;path&quot;:&quot;workspace/reports/q1-summary.md&quot;}" data-chat-id="chat-1" data-workspace-dir="/work/space" data-message-artifacts="[{&quot;id&quot;:&quot;file-1&quot;,&quot;filename&quot;:&quot;q1-summary.md&quot;}]">workspace/reports/q1-summary.md</button>
      </p>
      <p>
      <button data-mock="deliverable" data-reference="{&quot;kind&quot;:&quot;artifact&quot;,&quot;id&quot;:&quot;abc123&quot;}" data-chat-id="chat-1" data-workspace-dir="/work/space" data-message-artifacts="[{&quot;id&quot;:&quot;file-1&quot;,&quot;filename&quot;:&quot;q1-summary.md&quot;}]">artifact:abc123</button>
      </p>
      <p>
      <code class="bg-[#f6f6f1] text-orange-700 dark:bg-gray-800 dark:text-orange-400 px-1 py-0.5 rounded text-sm font-normal">npm run build</code>
      </p>"
    `);
  });

  it('does not linkify deliverables while streaming', () => {
    expect(renderBody(INLINE_CODE, { isStreaming: true })).toMatchInlineSnapshot(`
      "<p>
      <code class="bg-[#f6f6f1] text-orange-700 dark:bg-gray-800 dark:text-orange-400 px-1 py-0.5 rounded text-sm font-normal">workspace/reports/q1-summary.md</code>
      </p>
      <p>
      <code class="bg-[#f6f6f1] text-orange-700 dark:bg-gray-800 dark:text-orange-400 px-1 py-0.5 rounded text-sm font-normal">artifact:abc123</code>
      </p>
      <p>
      <code class="bg-[#f6f6f1] text-orange-700 dark:bg-gray-800 dark:text-orange-400 px-1 py-0.5 rounded text-sm font-normal">npm run build</code>
      </p>"
    `);
  });

  it('maps external, bare, embeddable and internal links', () => {
    expect(renderBody(LINKS)).toMatchInlineSnapshot(`
      "<p>
      <a href="https://example.com/docs" target="_blank" rel="noopener noreferrer" class="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors">docs</a>
      </p>
      <p>
      <span class="block">
      <a href="https://example.com/page" target="_blank" rel="noopener noreferrer" class="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors">https://example.com/page</a>
      <div data-mock="og-card" data-url="https://example.com/page">
      </div>
      </span>
      </p>
      <p>
      <span class="block">
      <a href="https://www.youtube.com/watch?v=abc" target="_blank" rel="noopener noreferrer" class="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors">video</a>
      <div data-mock="embed" data-descriptor="{&quot;provider&quot;:&quot;youtube&quot;,&quot;href&quot;:&quot;https://www.youtube.com/watch?v=abc&quot;}">
      </div>
      </span>
      </p>
      <p>
      <a href="#top">top</a> and <a href="mailto:hi@example.com">mail</a>
      </p>"
    `);
  });

  it('drops embeds and link cards while streaming', () => {
    expect(renderBody(CARD_LINKS, { isStreaming: true })).toMatchInlineSnapshot(`
      "<p>
      <a href="https://example.com/page" target="_blank" rel="noopener noreferrer" class="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors">https://example.com/page</a>
      </p>
      <p>
      <a href="https://www.youtube.com/watch?v=abc" target="_blank" rel="noopener noreferrer" class="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors">video</a>
      </p>"
    `);
  });

  it('maps images and tables', () => {
    expect(renderBody(`![diagram](https://example.com/a.png)\n\n${TABLE}`)).toMatchInlineSnapshot(`
      "<p>
      <i data-mock="image" data-src="https://example.com/a.png" data-alt="diagram">
      </i>
      </p>
      <div data-mock="table" data-is-streaming="false">
      <thead>
      <tr>
      <th>h1</th>
      <th>h2</th>
      </tr>
      </thead>
      <tbody>
      <tr>
      <td>a</td>
      <td>b</td>
      </tr>
      </tbody>
      </div>"
    `);
  });

  it('tells the table whether the answer is still streaming', () => {
    expect(renderBody(TABLE)).toContain('data-is-streaming="false"');
    expect(renderBody(TABLE, { isStreaming: true })).toContain('data-is-streaming="true"');
  });

  it('maps vault links and thinking tags', () => {
    expect(renderBody('vault://0f3a-bc12\n\n<think>reasoning text</think>')).toMatchInlineSnapshot(`
      "<p>
      <div data-mock="vault" data-id="0f3a-bc12" data-chat-id="chat-1">
      </div>
      </p>
      <p>
      <div data-mock="think">reasoning text</div>
      </p>"
    `);
  });

  it('maps every citation kind and falls back to the bare marker', () => {
    expect(renderBody(CITATIONS, { sources: SOURCES })).toMatchInlineSnapshot(`
      "<p>
      <span data-mock="link-popover" data-url="https://example.com/a" data-title="Web title" data-description="Web summary" data-site-name="Example" data-authority="Official" data-date="2026-01-02">1</span> <span data-mock="link-popover" data-url="#" data-title="Git skill" data-description="git_log: abc123

      git_diff: ">2</span> <button type="button" class="bg-secondary px-1 rounded ml-1 no-underline text-xs text-black/70 dark:text-white/70 relative hover:bg-amber-500/30 hover:text-amber-800 dark:hover:text-amber-300 transition-colors duration-200 cursor-pointer inline-flex items-center">3</button> <span data-mock="link-popover" data-url="#" data-title="empty.md" data-description="">4</span> <span data-mock="link-popover" data-url="#" data-title="Earlier chat" data-description="Earlier snippet">5</span> <span data-mock="link-popover" data-url="#" data-title="No URL">6</span> [9] [x]</p>"
    `);
  });

  it('hands the knowledge-base source to the drawer with every field in place', () => {
    const { container } = renderContent(CITATIONS, { sources: SOURCES });
    const drawer = () => container.querySelector('[data-mock="kb-drawer"]');
    expect(drawer()?.getAttribute('data-open')).toBe('false');

    fireEvent.click(screen.getByRole('button', { name: '3' }));

    expect(Object.fromEntries(Array.from(drawer()?.attributes ?? [], ({ name, value }) => [name, value])))
      .toMatchInlineSnapshot(`
        {
          "data-claim-confidence": "0.5",
          "data-claim-status": "contested",
          "data-claim-text": "Claim text",
          "data-context-key": "chat:msg-characterization",
          "data-level": "L2",
          "data-mock": "kb-drawer",
          "data-open": "true",
          "data-resource-uri": "raw/budget.md@sha",
          "data-section": "kb_section_index_routing",
          "data-snapshot-status": "stale",
          "data-snippet": "KB snippet",
          "data-superseded-from-uri": "raw/old.md",
          "data-surface": "chat",
          "data-thumbnail-url": "asset://agent-1/chart.png",
          "data-title": "budget.md § kb_section_index_routing",
        }
      `);
  });
});
