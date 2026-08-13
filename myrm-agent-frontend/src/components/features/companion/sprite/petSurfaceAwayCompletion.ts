/**
 * [INPUT]
 * (none — browser CustomEvent only)
 *
 * [OUTPUT]
 * - PET_SURFACE_AWAY_COMPLETION_EVENT
 * - dispatchPetSurfaceAwayCompletion: emit when a turn completes while user is away
 *
 * [POS]
 * Shared completion → pet mail unread signal. Same visibility gate as completionSound
 * (hidden tab or unfocused window), independent of sound/notification settings.
 */

export const PET_SURFACE_AWAY_COMPLETION_EVENT = 'pet-surface-away-completion';

export function dispatchPetSurfaceAwayCompletion(): void {
  if (typeof document === 'undefined') {return;}
  if (!document.hidden && document.hasFocus()) {return;}
  window.dispatchEvent(new CustomEvent(PET_SURFACE_AWAY_COMPLETION_EVENT));
}
