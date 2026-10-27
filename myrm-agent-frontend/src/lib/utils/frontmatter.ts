/**
 * Leading YAML front matter of a markdown document.
 *
 * [INPUT]
 * - content: markdown text, possibly opening with a `---` block of YAML keys
 *
 * [OUTPUT]
 * - stripYamlFrontmatter: the text without that block
 *
 * [POS]
 * The one place that decides what counts as front matter, so skills, wiki pages and workspace documents agree.
 * A block only counts when its first line is a `key:` line: a document that opens with a horizontal rule and has
 * another further down must not lose the text in between.
 */

const FRONTMATTER = /^\uFEFF?---[ \t]*\r?\n(?=[\w"'.-][^\r\n]*?:(?:[ \t]|\r?\n|$))[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/;

export function stripYamlFrontmatter(content: string): string {
  const match = FRONTMATTER.exec(content);
  return match ? content.slice(match[0].length) : content;
}
