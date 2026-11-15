/**
 * [INPUT]
 * (none)
 *
 * [OUTPUT]
 * - focusMessageInput: Moves the cursor to the end of the message box.
 *
 * [POS]
 * Shared by every action that fills the composer on the user's behalf, so they can type the rest right away.
 * The box is found in the document rather than passed in because those actions live far from the composer.
 */

/** Waits one tick so the composer has rendered the text the caller just wrote. */
export function focusMessageInput(): void {
  window.setTimeout(() => {
    const inputElement = document.querySelector('textarea');
    if (inputElement instanceof HTMLTextAreaElement) {
      inputElement.focus();
      inputElement.setSelectionRange(inputElement.value.length, inputElement.value.length);
    }
  }, 50);
}
