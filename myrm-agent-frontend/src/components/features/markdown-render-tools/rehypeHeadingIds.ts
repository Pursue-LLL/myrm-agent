import { visit } from 'unist-util-visit';
import type { Plugin } from 'unified';
import type { Root, Element } from 'hast';

export interface RehypeHeadingIdsOptions {
  prefix?: string;
}

/**
 * A rehype plugin to add sequential IDs to headings (h1-h6).
 * This ensures stable anchor links during streaming markdown rendering,
 * avoiding the issue where text-based slugs change as text is appended.
 */
const rehypeHeadingIds: Plugin<[RehypeHeadingIdsOptions?], Root> = (options = {}) => {
  const prefix = options.prefix || 'toc-header';
  return (tree) => {
    let index = 0;
    visit(tree, 'element', (node: Element) => {
      if (/^h[1-6]$/.test(node.tagName)) {
        node.properties = node.properties || {};
        node.properties.id = `${prefix}-${index}`;
        index++;
      }
    });
  };
};

export default rehypeHeadingIds;
