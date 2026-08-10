/**
 * Unified timezone resolution for next-intl.
 *
 * next-intl requires an explicit `timeZone` so SSR and CSR render identical
 * date-time markup. Omitting it triggers ENVIRONMENT_FALLBACK on the server and
 * hydration mismatches in the browser. Use a stable env override when the
 * server host differs from the client (e.g. UTC containers), otherwise fall
 * back to the runtime local zone (server and browser agree in local single-box
 * deployments).
 */
export function getDefaultTimezone(): string {
  const override = process.env.NEXT_PUBLIC_DEFAULT_TIMEZONE?.trim();
  if (override) {
    return override;
  }
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}
