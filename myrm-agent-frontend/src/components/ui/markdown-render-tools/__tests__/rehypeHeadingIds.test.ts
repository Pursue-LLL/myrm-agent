import { describe, it, expect } from 'vitest';
import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import rehypeRaw from 'rehype-raw';
import rehypeStringify from 'rehype-stringify';
import rehypeHeadingIds from '../rehypeHeadingIds';

describe('rehypeHeadingIds', () => {
  const processMarkdown = async (markdown: string, prefix?: string) => {
    const file = await unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeHeadingIds, prefix ? { prefix } : undefined)
      .use(rehypeStringify)
      .process(markdown);
    return String(file);
  };

  it('should add sequential IDs to markdown headings', async () => {
    const markdown = `
# Heading 1
## Heading 2
### Heading 3
    `;
    const html = await processMarkdown(markdown);
    expect(html).toContain('id="toc-header-0"');
    expect(html).toContain('id="toc-header-1"');
    expect(html).toContain('id="toc-header-2"');
  });

  it('should use the provided prefix', async () => {
    const markdown = `
# Heading 1
## Heading 2
    `;
    const html = await processMarkdown(markdown, 'custom-prefix');
    expect(html).toContain('id="custom-prefix-0"');
    expect(html).toContain('id="custom-prefix-1"');
  });

  it('should correctly assign IDs to raw HTML headings', async () => {
    const markdown = `
# Markdown Heading

<h1>HTML Heading</h1>

## Another Markdown Heading
    `;
    const html = await processMarkdown(markdown);
    // 验证原生 HTML 标签也被正确分配了 ID，且索引是连续的
    expect(html).toContain('<h1 id="toc-header-0">Markdown Heading</h1>');
    expect(html).toContain('<h1 id="toc-header-1">HTML Heading</h1>');
    expect(html).toContain('<h2 id="toc-header-2">Another Markdown Heading</h2>');
  });

  it('should ignore headings inside code blocks', async () => {
    const markdown = `
# Real Heading
\`\`\`html
<h1>Fake Heading</h1>
\`\`\`
## Another Real Heading
    `;
    const html = await processMarkdown(markdown);
    expect(html).toContain('<h1 id="toc-header-0">Real Heading</h1>');
    expect(html).not.toContain('id="toc-header-1">Fake Heading');
    expect(html).toContain('<h2 id="toc-header-1">Another Real Heading</h2>');
  });
});
