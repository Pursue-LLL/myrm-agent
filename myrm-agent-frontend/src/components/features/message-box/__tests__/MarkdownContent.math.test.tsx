/** @vitest-environment jsdom */
/**
 * 公式在 MarkdownContent 里的整条链路：文本预处理、解析层规则、归一化与 KaTeX 渲染按正确的顺序接在 react-markdown 上。
 * 规则本身的细节（边界用例、代码保护）在 lib/utils/__tests__/markdownMath.test.ts，这里只证明接线。
 */
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/hooks/message-input/useSmoothStream', () => ({
  useSmoothStream: () => ({ addChunk: vi.fn(), displayedContent: '', flush: vi.fn(), reset: vi.fn() }),
}));
vi.mock('@/store/useConfigStore', () => ({ default: () => false }));
vi.mock('@/services/wiki/evidenceMetrics', () => ({ recordEvidenceSurface: vi.fn() }));
vi.mock('@/components/features/markdown-render-tools/CodeBlock', () => ({
  default: ({ value }: { value: string }) => <pre>{value}</pre>,
}));
vi.mock('@/components/features/markdown-render-tools/LinkPopover', () => ({ default: () => null }));
vi.mock('@/components/features/markdown-render-tools/InlineHtmlWidget', () => ({ default: () => null }));
vi.mock('@/components/features/markdown-render-tools/MermaidChart', () => ({ default: () => null }));
vi.mock('@/components/features/markdown-render-tools/InlineDiffViewer', () => ({ default: () => null }));
vi.mock('@/components/features/markdown-render-tools/MarkdownImage', () => ({ default: () => null }));
vi.mock('@/components/features/artifacts/VaultArtifactCard', () => ({ default: () => null }));
vi.mock('../DeliverableReferenceLink', () => ({ default: () => null }));
vi.mock('../SourceChunkDrawer', () => ({ default: () => null }));

import MarkdownContent from '../MarkdownContent';

function renderMarkdown(content: string, isStreaming = false): HTMLElement {
  return render(<MarkdownContent content={content} sources={[]} messageId="msg-math" isStreaming={isStreaming} />)
    .container;
}

const formulaCount = (container: HTMLElement) => container.querySelectorAll('.katex').length;

describe('MarkdownContent math', () => {
  it('renders every formula notation with KaTeX', () => {
    const container = renderMarkdown('Inline $a+b$ and \\(c+d\\).\n\n$$\ne^{i\\pi}=-1\n$$\n\nThen \\[f(x)\\].');
    expect(formulaCount(container)).toBe(4);
    expect(container.querySelectorAll('.katex-display')).toHaveLength(1);
    expect(container.querySelectorAll('.katex-error')).toHaveLength(0);
  });

  it('leaves prices, shell variables and code as written', () => {
    const container = renderMarkdown('Plans cost $5 and $10; set $JAVA_HOME and $PATH. Run `echo $5 $6`.');
    expect(formulaCount(container)).toBe(0);
    expect(container.textContent).toContain('Plans cost $5 and $10; set $JAVA_HOME and $PATH. Run echo $5 $6.');
  });

  it('keeps a real formula next to prices', () => {
    const container = renderMarkdown('It costs $5 and the area is $\\pi r^2$, or $7.');
    expect(formulaCount(container)).toBe(1);
    expect(container.textContent).toContain('It costs $5 and the area is ');
    expect(container.textContent).toContain(', or $7.');
  });

  it('shows an unfinished $$ as text while streaming instead of an error', () => {
    const container = renderMarkdown('The solution is $$\\frac{1}{', true);
    expect(formulaCount(container)).toBe(0);
    expect(container.querySelectorAll('.katex-error')).toHaveLength(0);
    expect(container.textContent).toContain('The solution is $$\\frac{1}{');
  });

  it('escapes the percent sign inside a formula but not in prose', () => {
    const container = renderMarkdown('Up 100% overall, then $$50% \\text{done}$$');
    expect(formulaCount(container)).toBe(1);
    expect(container.textContent).toContain('Up 100% overall');
    expect(container.textContent).toContain('done');
  });

  it('lets the SVG KaTeX draws for roots and vectors through the element whitelist', () => {
    const container = renderMarkdown('The root $\\sqrt{x}$ and the vector $\\vec{v}$.');
    expect(container.querySelectorAll('.katex svg path').length).toBeGreaterThan(0);
  });

  it('unwraps SVG the model writes itself and keeps its text', () => {
    const container = renderMarkdown(
      'Before <svg viewBox="0 0 8 8"><path d="M0 0L8 8"></path><line x1="0" x2="8"></line>inside</svg> after',
    );
    expect(container.querySelectorAll('svg, path, line')).toHaveLength(0);
    expect(container.textContent).toContain('Before inside after');
  });

  it('does not let a message keep SVG by wrapping it in the markup of a formula', () => {
    const container = renderMarkdown('<span class="katex"><svg><path d="M0 0L8 8"></path></svg></span>');
    expect(container.querySelectorAll('svg')).toHaveLength(0);
  });
});
