/**
 * User presence.
 *
 * [INPUT]
 * (none — reads the browser document)
 *
 * [OUTPUT]
 * - isUserPresent: true while the page is visible and its window has focus
 *
 * [POS]
 * Single definition of "the user is looking at this page", shared by away-only alerts
 * (completion sound, pet mail) and the Catchup presence stamp.
 */

export function isUserPresent(): boolean {
  if (typeof document === 'undefined') {
    return false;
  }
  return !document.hidden && document.hasFocus();
}
