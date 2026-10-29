/**
 * [INPUT]
 * - dev-ports.mjs::sharedFrontendPort (POS: Default ports of the user, shared dev and isolated stacks — SSOT)
 *
 * [OUTPUT]
 * - resolveCleanupPort: the UI port `bun run cleanup` reclaims
 *
 * [POS]
 * Kept apart from `cleanup-targets.ts`: this one reaches outside the frontend directory for the
 * port SSOT, while `cleanup-targets.ts` is loaded by `next.config.ts` through the pause gate and
 * must stay self-contained so a frontend-only production build never depends on dev tooling.
 */
import { sharedFrontendPort } from '../../scripts/dev/lib/dev-ports.mjs';

/** An explicit `MYRM_FRONTEND_PORT` wins; otherwise the shared dev UI (3000 is the user's stack). */
export function resolveCleanupPort(): number {
  const explicit = Number.parseInt(process.env.MYRM_FRONTEND_PORT ?? '', 10);
  return Number.isInteger(explicit) && explicit > 0 && explicit <= 65535
    ? explicit
    : sharedFrontendPort();
}
