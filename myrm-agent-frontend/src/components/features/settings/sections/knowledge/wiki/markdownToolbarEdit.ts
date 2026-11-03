/**
 * [INPUT]
 * - ./WikiEditorToolbar: ToolbarAction
 *
 * [OUTPUT]
 * - MarkdownSnippetCopy: the placeholder words inserted when the toolbar acts on an empty selection
 * - ToolbarEdit: the text to put in place of the selection, and the span to select afterwards
 * - buildToolbarEdit: Markdown for one toolbar action applied to the selected text
 *
 * [POS]
 * Pure text rules of the Wiki editor toolbar. The placeholder words come from the caller (the user's language), and
 * the span selected after an insert is measured from the placeholder itself, so the user can type over it at once.
 */

import type { ToolbarAction } from './WikiEditorToolbar';

export interface MarkdownSnippetCopy {
  bold: string;
  italic: string;
  heading: string;
  code: string;
  quote: string;
  bullet: string;
  todo: string;
  wikilink: string;
  tableHeader: (index: number) => string;
  tableCell: (index: number) => string;
}

export interface ToolbarEdit {
  text: string;
  /** Characters to select after the insert, counted from the start of the inserted text; absent keeps the caret. */
  select?: { startOffset: number; length: number };
}

/** Wraps `selectedText`, or the placeholder when nothing is selected, in a marker pair; the placeholder is selected. */
function wrap(open: string, close: string, selectedText: string, placeholder: string): ToolbarEdit {
  if (selectedText) {
    return { text: `${open}${selectedText}${close}` };
  }
  return { text: `${open}${placeholder}${close}`, select: { startOffset: open.length, length: placeholder.length } };
}

function block(prefix: string, selectedText: string, placeholder: string): ToolbarEdit {
  return { text: `\n${prefix}${selectedText || placeholder}\n` };
}

export function buildToolbarEdit(action: ToolbarAction, selectedText: string, copy: MarkdownSnippetCopy): ToolbarEdit {
  switch (action) {
    case 'bold':
      return wrap('**', '**', selectedText, copy.bold);
    case 'italic':
      return wrap('*', '*', selectedText, copy.italic);
    case 'h2':
      return block('## ', selectedText, copy.heading);
    case 'code':
      if (selectedText.includes('\n')) {
        return { text: `\n\`\`\`markdown\n${selectedText}\n\`\`\`\n` };
      }
      return wrap('`', '`', selectedText, copy.code);
    case 'quote':
      return block('> ', selectedText, copy.quote);
    case 'bullet':
      return block('- ', selectedText, copy.bullet);
    case 'todo':
      return block('- [ ] ', selectedText, copy.todo);
    case 'wikilink':
      return wrap('[[', ']]', selectedText, copy.wikilink);
    case 'table':
      return {
        text: `\n| ${copy.tableHeader(1)} | ${copy.tableHeader(2)} |\n| --- | --- |\n| ${copy.tableCell(1)} | ${copy.tableCell(2)} |\n`,
      };
  }
}
