/**
 * Sentry Client-side Configuration
 *
 * Controlled by environment variables:
 * - NEXT_PUBLIC_SENTRY_ENABLED: Enable/disable Sentry (default: false)
 * - NEXT_PUBLIC_SENTRY_DSN: Sentry project DSN (required if enabled)
 * - NEXT_PUBLIC_SENTRY_ENVIRONMENT: Environment name (default: production)
 * - NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE: Performance sampling 0.0-1.0 (default: 0.1)
 * - NEXT_PUBLIC_SENTRY_REPLAYS_SESSION_SAMPLE_RATE: Session replay sampling (default: 0.0)
 * - NEXT_PUBLIC_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE: Error replay sampling (default: 1.0)
 *
 * Design:
 * - Frontend layer uses Sentry for APM (errors + performance)
 * - Integrates with backend trace_id for cross-layer correlation
 * - Lightweight: disabled by default to avoid overhead
 */

import * as Sentry from "@sentry/nextjs";

const SENTRY_ENABLED = process.env.NEXT_PUBLIC_SENTRY_ENABLED === "true";

if (SENTRY_ENABLED) {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

  if (!dsn) {
    console.error("[Sentry] NEXT_PUBLIC_SENTRY_DSN not set, skipping initialization");
  } else {
    Sentry.init({
      dsn,
      environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "production",

      // Performance Monitoring
      tracesSampleRate: parseFloat(
        process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE || "0.1"
      ),

      // Session Replay (optional)
      replaysSessionSampleRate: parseFloat(
        process.env.NEXT_PUBLIC_SENTRY_REPLAYS_SESSION_SAMPLE_RATE || "0.0"
      ),
      replaysOnErrorSampleRate: parseFloat(
        process.env.NEXT_PUBLIC_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE || "1.0"
      ),

      // Integrations
      integrations: [
        Sentry.browserTracingIntegration(),
        Sentry.replayIntegration({
          // Capture replays on errors only (not all sessions)
          maskAllText: true,
          blockAllMedia: true,
        }),
      ],
      tracePropagationTargets: [
        "localhost",
        /^https:\/\/[^/]+\.myrm\.ai/,
        /^\/api\//,
      ],

      // Ignore common errors
      ignoreErrors: [
        "ResizeObserver loop limit exceeded",
        "Non-Error promise rejection captured",
        "AbortError",
      ],

      // Before send hook for custom processing
      beforeSend(event, _hint) {
        // Add custom context from backend trace_id if available
        const traceId = window.__MYRM_TRACE_ID__;
        if (traceId) {
          event.tags = { ...event.tags, backend_trace_id: traceId };
        }
        return event;
      },
    });

    console.log(
      "[Sentry] Client initialized:",
      "env=",
      process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT,
      "tracesSampleRate=",
      process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE
    );
  }
} else {
  console.debug("[Sentry] Disabled (NEXT_PUBLIC_SENTRY_ENABLED=false)");
}
