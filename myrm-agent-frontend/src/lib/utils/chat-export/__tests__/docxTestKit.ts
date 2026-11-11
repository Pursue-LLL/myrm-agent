/**
 * [INPUT] jszip::JSZip (reads the .docx archive); the jsdom DOMParser (parses each XML part).
 * [OUTPUT] DocxPackage, openDocx, parseXml, elements, wordText, paragraphTexts, externalTargets, hasIllegalXmlChar.
 * [POS] Test kit of the Word export: opens the file `buildDocxBlob` wrote and exposes the parts a test asserts on, so a test checks what Word will read and not how the converter was called.
 */
import JSZip from 'jszip';

export interface DocxPackage {
  /** Every XML part (`*.xml`, `*.rels`) by its path in the archive. */
  parts: Record<string, string>;
  /** `word/document.xml`, parsed. */
  document: XMLDocument;
  /** The paths under `word/media/`. */
  media: string[];
}

/** Whether the text holds a character XML 1.0 does not allow: a control character, U+FFFE, U+FFFF or a lone surrogate. */
export function hasIllegalXmlChar(text: string): boolean {
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    if (code < 0x20 && code !== 0x09 && code !== 0x0a && code !== 0x0d) {
      return true;
    }
    if (code === 0xfffe || code === 0xffff) {
      return true;
    }
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = text.charCodeAt(i + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        return true;
      }
      i += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return true;
    }
  }
  return false;
}

/** Parses XML and fails on anything a strict reader would refuse, which the browser reports as a `parsererror`. */
export function parseXml(xml: string): XMLDocument {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  const error = doc.getElementsByTagName('parsererror')[0];
  if (error) {
    throw new Error(`Not well-formed XML: ${error.textContent}`);
  }
  return doc;
}

export async function openDocx(blob: Blob): Promise<DocxPackage> {
  const zip = await JSZip.loadAsync(await blob.arrayBuffer());
  const parts: Record<string, string> = {};
  for (const name of Object.keys(zip.files)) {
    if (/\.(xml|rels)$/.test(name)) {
      parts[name] = await zip.files[name].async('string');
    }
  }
  const body = parts['word/document.xml'];
  if (body === undefined) {
    throw new Error('The Word file has no word/document.xml');
  }
  return {
    parts,
    document: parseXml(body),
    media: Object.keys(zip.files).filter((name) => name.startsWith('word/media/') && !zip.files[name].dir),
  };
}

export const elements = (root: Document | Element, qualifiedName: string): Element[] => [
  ...root.getElementsByTagName(qualifiedName),
];

/** The text under a node as Word shows it: runs joined, each line break as `\n` (an equation's text is not text). */
export function wordText(root: Document | Element): string {
  return elements(root, '*')
    .map((node) => {
      if (node.tagName === 'w:t') {
        return node.textContent ?? '';
      }
      return node.tagName === 'w:br' ? '\n' : '';
    })
    .join('');
}

export const paragraphTexts = (root: Document | Element): string[] => elements(root, 'w:p').map(wordText);

/** The addresses the file's links point to, from a relationships part (`word/_rels/document.xml.rels`). */
export function externalTargets(relsXml: string): string[] {
  return elements(parseXml(relsXml), 'Relationship')
    .filter((rel) => rel.getAttribute('TargetMode') === 'External')
    .map((rel) => rel.getAttribute('Target') ?? '');
}
