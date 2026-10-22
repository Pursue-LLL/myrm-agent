/**
 * [OUTPUT]
 * - SendIcon / SkipIcon / CheckCircleIcon: action and answered-state icons
 * - clarificationTextareaClass: free-text answer textarea styling
 * - resolveClarificationShellClass / resolveClarificationGradientClass / resolveClarificationBadgeClass:
 *   card chrome, amber when the form asks for a risk confirmation
 *
 * [POS]
 * Visual shell primitives of ClarificationInput; no state and no submission logic.
 */

export const SendIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M22 2 11 13" />
    <path d="M22 2 15 22 11 13 2 9z" />
  </svg>
);

export const SkipIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <polygon points="5 4 15 12 5 20 5 4" />
    <line x1="19" y1="5" x2="19" y2="19" />
  </svg>
);

export const CheckCircleIcon = ({ className }: { className?: string }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

export const clarificationTextareaClass =
  'w-full resize-none rounded-xl border border-border/70 bg-background/90 px-3 py-2.5 text-sm leading-relaxed placeholder:text-muted-foreground transition-colors focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/25 sm:px-4 sm:py-3';

export function resolveClarificationShellClass(requiresConfirmation?: boolean): string {
  if (requiresConfirmation) {
    return 'relative overflow-hidden rounded-2xl border border-amber-500/40 bg-card/90 backdrop-blur-xl';
  }
  return 'relative overflow-hidden rounded-2xl border border-border/60 bg-card/90 backdrop-blur-xl';
}

export function resolveClarificationGradientClass(requiresConfirmation?: boolean): string {
  if (requiresConfirmation) {
    return 'pointer-events-none absolute inset-0 bg-gradient-to-br from-amber-500/10 via-transparent to-orange-500/5 dark:from-amber-500/15 dark:to-orange-500/10';
  }
  return 'pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/8 via-transparent to-violet-500/5 dark:from-primary/12 dark:to-violet-500/8';
}

export function resolveClarificationBadgeClass(requiresConfirmation?: boolean): string {
  if (requiresConfirmation) {
    return 'shrink-0 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-amber-700 dark:text-amber-300';
  }
  return 'shrink-0 rounded-full border border-primary/25 bg-primary/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-primary';
}
