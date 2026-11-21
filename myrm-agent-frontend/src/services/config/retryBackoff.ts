/**
 * [OUTPUT]
 * RetryBackoff: one pending retry whose pause doubles from 1 s up to a minute.
 *
 * [POS]
 * Pacing of the outbox retries for changes the backend did not take. At most one retry is pending however many
 * failures ask for one, and the pause starts over once the backend has answered. It knows nothing about what is retried.
 */

const MIN_PAUSE_MS = 1000;
const MAX_PAUSE_MS = 60_000;

export class RetryBackoff {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private pause = MIN_PAUSE_MS;

  constructor(private readonly retry: () => void) {}

  /** Arms the retry unless one is pending; the pause after this one doubles. */
  schedule(): void {
    if (this.timer) {
      return;
    }
    this.timer = setTimeout(() => {
      this.timer = null;
      this.retry();
    }, this.pause);
    this.pause = Math.min(this.pause * 2, MAX_PAUSE_MS);
  }

  /** The backend answered: the next pause is the shortest again. */
  reset(): void {
    this.pause = MIN_PAUSE_MS;
  }

  /** Drops the pending retry. */
  cancel(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}
