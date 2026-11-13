/**
 * [INPUT]
 * - events::EventEmitter (type only; POS: the stdio streams being guarded)
 *
 * [OUTPUT]
 * - installDevStdioGuard
 *
 * [POS]
 * Keeps a failed log write from taking `next dev` down or into a loop. Once whoever reads its
 * stdout/stderr is gone (closed pipe or socket, hung-up terminal) every write fails with EPIPE, EIO or
 * ECONNRESET; Node ignores SIGPIPE, so each failure surfaces as an `error` event on the stream, and
 * stdout/stderr reset themselves after each one, so the next write fails again. With nobody listening
 * the event is an uncaught exception, and Next's own `uncaughtException` handlers log through the very
 * stream that just failed: the log write fails, becomes uncaught again, and re-enters them without end
 * (one pegged core, memory growing without bound). A log line nobody can read is not worth the server,
 * so the errors are absorbed; whether the server should keep running without a reader is left to whoever
 * launched it.
 * Installed from next.config.ts, so it covers a raw `next dev` that no supervisor wraps. Self-contained:
 * next.config.ts imports it statically and the Docker builder copies only this package.
 */
import type { EventEmitter } from 'events';

/** Process-wide key (not module state): Next evaluates next.config.ts again on reload and must not stack listeners. */
const GUARDED = Symbol.for('myrm.devStdioGuard.installed');

export function installDevStdioGuard(streams: readonly EventEmitter[] = [process.stdout, process.stderr]): void {
  for (const stream of streams) {
    if (Reflect.has(stream, GUARDED)) {
      continue;
    }
    Reflect.set(stream, GUARDED, true);
    stream.on('error', () => undefined);
  }
}
