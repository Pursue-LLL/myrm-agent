/**
 * [INPUT] ./chatExportDocxImages.ts::rehypeWordImages (POS: which images the Word file embeds); ./exportUrlPolicy.ts::isSafeLinkUrl (POS: which link targets an exported file may keep); ../markdownMath.ts::mathPlugins, normalizeMathDelimiters (POS: which `$` are formulas and how they render); docx::Document, Packer, ShadingType (POS: the Word file); docx/html::htmlToContent (POS: HTML to Word headings, lists, tables, footnotes, task-list checkboxes and, from KaTeX's MathML, native equations).
 * [OUTPUT] buildDocxBlob.
 * [POS] Markdown-to-Word export of one chat message. The Word file is written from the message's own HTML and not from the exported web page, whose theme button, copy buttons and script a Word file has no use for.
 */
import { Document, Packer, ShadingType } from 'docx';
import { htmlToContent } from 'docx/html';
import type { Element, Root as HastRoot } from 'hast';
import type { Parents, PhrasingContent, Root as MdastRoot } from 'mdast';
import rehypeStringify from 'rehype-stringify';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { unified, type Plugin } from 'unified';
import { visit } from 'unist-util-visit';
import { rehypeWordImages } from './chatExportDocxImages';
import { isSafeLinkUrl } from './exportUrlPolicy';
import { mathPlugins, normalizeMathDelimiters } from '../markdownMath';

const AUTHOR = 'Myrm';
const CODE_SHADE = 'F2F2F2';

const BREAK_TAG = /^<br\s*\/?>$/i;
/** A standalone .docx has no base address, so only a link that carries its own can work. */
const ABSOLUTE_LINK = /^(?:https?:|mailto:|tel:)/i;

type PhrasingParent = Extract<Parents, { children: PhrasingContent[] }>;

/** The parents a line break may sit in: elsewhere a `<br>` is a block of raw HTML and has no line to break. */
const PHRASING_PARENTS: ReadonlySet<string> = new Set([
  'paragraph',
  'heading',
  'emphasis',
  'strong',
  'delete',
  'link',
  'linkReference',
  'tableCell',
]);

const holdsPhrasing = (parent: Parents): parent is PhrasingParent => PHRASING_PARENTS.has(parent.type);

/** Raw HTML is not parsed, so `<br>` (how a model breaks a line inside a table cell) would vanish; it becomes a real break. */
const remarkBreakTags: Plugin<[], MdastRoot> = () => (tree) => {
  visit(tree, 'html', (node, index, parent) => {
    if (parent && index !== undefined && holdsPhrasing(parent) && BREAK_TAG.test(node.value.trim())) {
      parent.children[index] = { type: 'break' };
    }
  });
};

/**
 * Only an address that works outside the page stays a link; any other keeps its text (Word on Windows reads `//host`
 * as a network path). A footnote reference is the one in-page link left alone, because the converter turns it into a
 * Word footnote; the arrow back to the reference only helps on a web page and goes.
 */
const rehypeWordLinks: Plugin<[], HastRoot> = () => (tree) => {
  visit(tree, 'element', (node: Element, index, parent): number | undefined => {
    if (node.tagName !== 'a') {
      return undefined;
    }
    // The parser gives the back-reference an empty string, so only its presence tells it apart.
    if (node.properties.dataFootnoteBackref !== undefined && parent && index !== undefined) {
      parent.children.splice(index, 1);
      return index;
    }
    const href = node.properties.href;
    if (
      typeof href === 'string' &&
      !node.properties.dataFootnoteRef &&
      !(ABSOLUTE_LINK.test(href) && isSafeLinkUrl(href))
    ) {
      node.tagName = 'span';
      node.properties = {};
    }
    return undefined;
  });
};

const wordHtmlProcessor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(mathPlugins.remark)
  .use(remarkBreakTags)
  .use(remarkRehype, { allowDangerousHtml: false })
  .use(mathPlugins.rehype)
  .use(rehypeWordLinks)
  .use(rehypeWordImages)
  .use(rehypeStringify);

const CODE_SHADING = { type: ShadingType.CLEAR, color: 'auto', fill: CODE_SHADE } as const;

/** The two styles the converter's style map points at (`pre` and `code`); every other element uses Word's own. */
const WORD_STYLES = {
  default: { document: { run: { font: 'Calibri', size: 22 }, paragraph: { spacing: { after: 120, line: 276 } } } },
  paragraphStyles: [
    {
      id: 'CodeBlock',
      name: 'Code Block',
      basedOn: 'Normal',
      quickFormat: true,
      run: { font: 'Courier New', size: 20 },
      paragraph: { shading: CODE_SHADING, spacing: { before: 60, after: 120, line: 240 } },
    },
  ],
  characterStyles: [{ id: 'InlineCode', name: 'Inline Code', run: { font: 'Courier New', shading: CODE_SHADING } }],
};

/** One message's Markdown as a Word file: native headings, lists, tables, task checkboxes, footnotes and equations. */
export async function buildDocxBlob(markdown: string): Promise<Blob> {
  const html = String(await wordHtmlProcessor.process(normalizeMathDelimiters(markdown)));
  const content = htmlToContent(html, { styleMap: { pre: 'CodeBlock', code: 'InlineCode' } });
  const doc = new Document({
    creator: AUTHOR,
    lastModifiedBy: AUTHOR,
    styles: WORD_STYLES,
    sections: [{ children: [...content] }],
  });
  return Packer.toBlob(doc);
}
