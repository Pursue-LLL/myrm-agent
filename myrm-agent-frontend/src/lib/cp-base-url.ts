/**
 * Control plane REST base URL for SaaS auth (OAuth, legacy email verify API).
 * Prefer page hostname so browser calls stay on localhost (not 127.0.0.1) for CORS/cookies.
 */
export function resolveCpBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_CP_BASE_URL?.trim();
  if (configured) return configured.replace(/\/+$/, '');
  if (typeof window !== 'undefined') {
    return `http://${window.location.hostname}:8003`;
  }
  return 'http://localhost:8003';
}
