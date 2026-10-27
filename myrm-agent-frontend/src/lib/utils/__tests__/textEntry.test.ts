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

  it('is true for what a code editor focuses: Monaco focuses a plain div, not a textarea', () => {
    const monaco = element('div');
    monaco.className = 'monaco-editor';
    const typingSurface = element('div', monaco);
    typingSurface.className = 'native-edit-context';
    const findToggle = element('div', monaco);
    findToggle.className = 'monaco-custom-toggle';

    expect(isTextEntry(typingSurface)).toBe(true);
    // The find widget lives inside the editor and uses Escape for itself.
    expect(isTextEntry(findToggle)).toBe(true);
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
