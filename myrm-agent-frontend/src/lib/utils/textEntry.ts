/**
 * Whether a key was typed into something that owns its keys.
 *
 * [INPUT]
 * - target: where a keyboard event was aimed
 *
 * [OUTPUT]
 * - isTextEntry: true for form fields, editable elements and the inside of a code editor
 * - SELF_MANAGED_EDITOR_SELECTOR: the editors that draw their own text surface
 *
 * [POS]
 * One answer for "is the user typing?", for the page-level shortcuts that must keep out of the way (Escape closing a
 * drawer, `/` jumping to the chat input). Code editors need naming because they do not look like fields: Monaco
 * focuses a plain `div` (its EditContext surface) that is neither a textarea nor contenteditable, and every
 * widget of the editor (find box, toggles) sits inside it.
 */

/** Editors that handle their own input, composition included; everything inside them is theirs. */
export const SELF_MANAGED_EDITOR_SELECTOR = '.monaco-editor, .cm-editor';

export function isTextEntry(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) ||
      target.closest(SELF_MANAGED_EDITOR_SELECTOR) !== null)
  );
}
