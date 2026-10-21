import { NextResponse } from 'next/server';

/**
 * Deprecated: this endpoint previously proxied arbitrary external model URLs.
 * Model discovery now runs through server-side SSRF-guarded
 * `/integrations/llm/discover-models`.
 */
export async function POST() {
  return NextResponse.json(
    {
      success: false,
      error: 'Endpoint deprecated. Use /integrations/llm/discover-models.',
    },
    { status: 410 },
  );
}
