/** @vitest-environment jsdom */
import { afterEach, describe, expect, it } from 'vitest';
import { isTextEntry, SELF_MANAGED_EDITOR_SELECTOR } from '../textEntry';

const attached: HTMLElement[] = [];

function element<K extends keyof HTMLElementTagNameMap>(tag: K, parent: HTMLElement = document.body) {
  const node = parent.appendChild(document.createElement(tag));
  attached.push(node);
  return node;
}

afterEach(() => {
  attached.splice(0).forEach((node) => node.remove());
});

describe('isTextEntry', () => {
  it.each(['input', 'textarea', 'select'] as const)('is true for a %s', (tag) => {
    expect(isTextEntry(element(tag))).toBe(true);
  });

  it('is true for an editable element, which jsdom does not flag by itself', () => {
    const editable = element('div');
    Object.defineProperty(editable, 'isContentEditable', { value: true });

    expect(isTextEntry(editable)).toBe(true);
  });

  /** What Monaco focuses: a plain div, whose `aria-autocomplete` is `both` while editable and `list` with the suggest list open. */
  function monacoTypingSurface(autocomplete: string | null) {
    const monaco = element('div');
    monaco.className = 'monaco-editor';
    const typingSurface = element('div', monaco);
    typingSurface.className = 'native-edit-context';
    if (autocomplete !== null) {
      typingSurface.setAttribute('aria-autocomplete', autocomplete);
    }
    return { monaco, typingSurface };
  }

  it.each(['both', 'list'])('is true for what an editable Monaco focuses (aria-autocomplete="%s")', (autocomplete) => {
    expect(isTextEntry(monacoTypingSurface(autocomplete).typingSurface)).toBe(true);
  });

  it('is true for a Monaco surface that does not say whether it is read-only', () => {
    expect(isTextEntry(monacoTypingSurface(null).typingSurface)).toBe(true);
  });

  it('is false for what a read-only Monaco focuses: nothing can be typed, so the page shortcuts stay available', () => {
    expect(isTextEntry(monacoTypingSurface('none').typingSurface)).toBe(false);
  });

  it('is true for the widgets of a code editor, read-only or not: the find box takes text and uses Escape itself', () => {
    const { monaco } = monacoTypingSurface('none');
    const findToggle = element('div', monaco);
    findToggle.className = 'monaco-custom-toggle';
    const findBox = element('textarea', monaco);
    findBox.className = 'input';

    expect(isTextEntry(findToggle)).toBe(true);
    expect(isTextEntry(findBox)).toBe(true);
  });

  it('is true inside CodeMirror too', () => {
    const codeMirror = element('div');
    codeMirror.className = 'cm-editor';
    const content = element('div', codeMirror);
    content.className = 'cm-content';

    expect(isTextEntry(content)).toBe(true);
  });

  it('is false for everything else', () => {
    expect(isTextEntry(element('div'))).toBe(false);
    expect(isTextEntry(element('button'))).toBe(false);
    expect(isTextEntry(document.body)).toBe(false);
    expect(isTextEntry(window)).toBe(false);
    expect(isTextEntry(null)).toBe(false);
  });

  it('shares its idea of a self-managed editor with the input-method guard', () => {
    expect(SELF_MANAGED_EDITOR_SELECTOR).toContain('.monaco-editor');
    expect(SELF_MANAGED_EDITOR_SELECTOR).toContain('.cm-editor');
  });
});
