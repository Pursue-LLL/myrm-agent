/**
 * Whether a key was typed into something that owns its keys.
 *
 * [INPUT]
 * - target: where a keyboard event was aimed
 *
 * [OUTPUT]
 * - isTextEntry: true for form fields, editable elements and the inside of a code editor that takes text
 * - SELF_MANAGED_EDITOR_SELECTOR: the editors that draw their own text surface
 *
 * [POS]
 * One answer for "is the user typing?", for the page-level shortcuts that must keep out of the way (Escape closing a
 * drawer, `/` jumping to the chat input). Code editors need naming because they do not look like fields: Monaco
 * focuses a plain `div` (its EditContext surface) that is neither a textarea nor contenteditable, and every
 * widget of the editor (find box, toggles) sits inside it. A read-only Monaco (an approval card, a diff) takes no
 * text, so the surface it focuses is not a text entry: Monaco marks that surface `aria-autocomplete="none"`, where
 * an editable one says `both` (or `list` with the suggest list open).
 */

/** Editors that handle their own input, composition included; everything inside them is theirs. */
export const SELF_MANAGED_EDITOR_SELECTOR = '.monaco-editor, .cm-editor';

/** The `aria-autocomplete` value of the surface a read-only Monaco focuses. */
const READ_ONLY_SURFACE_AUTOCOMPLETE = 'none';

export function isTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) {
    return true;
  }
  return (
    target.closest(SELF_MANAGED_EDITOR_SELECTOR) !== null &&
    target.getAttribute('aria-autocomplete') !== READ_ONLY_SURFACE_AUTOCOMPLETE
  );
}
