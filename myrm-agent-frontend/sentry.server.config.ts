/**
 * Sentry Server-side Configuration
 *
 * Controlled by environment variables (same as client):
 * - NEXT_PUBLIC_SENTRY_ENABLED: Enable/disable Sentry
 * - NEXT_PUBLIC_SENTRY_DSN: Sentry project DSN
 * - NEXT_PUBLIC_SENTRY_ENVIRONMENT: Environment name
 * - NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE: Performance sampling
 *
 * Design:
 * - Server-side monitoring for API routes and SSR errors
 * - Separate from client config for different runtime environments
 */

import * as Sentry from "@sentry/nextjs";

const SENTRY_ENABLED = process.env.NEXT_PUBLIC_SENTRY_ENABLED === "true";

if (SENTRY_ENABLED) {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

  if (!dsn) {
    console.error("[Sentry] NEXT_PUBLIC_SENTRY_DSN not set, skipping server initialization");
  } else {
    Sentry.init({
      dsn,
      environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "production",

      // Performance Monitoring
      tracesSampleRate: parseFloat(
        process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE || "0.1"
      ),

      // Server-specific integrations
      integrations: [
        Sentry.httpIntegration(),
      ],

      // Before send hook for server-side processing
      beforeSend(event, _hint) {
        // Filter out low-priority server errors
        if (event.level === "warning") {
          return null; // Drop warnings
        }
        return event;
      },
    });

    console.log(
      "[Sentry] Server initialized:",
      "env=",
      process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT,
      "tracesSampleRate=",
      process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE
    );
  }
} else {
  console.debug("[Sentry] Server disabled (NEXT_PUBLIC_SENTRY_ENABLED=false)");
}
