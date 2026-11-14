import { NextResponse } from 'next/server';

/**
 * Deprecated: this endpoint proxies nothing. Model discovery runs through the server-side
 * SSRF-guarded `/integrations/llm/discover-models`.
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
