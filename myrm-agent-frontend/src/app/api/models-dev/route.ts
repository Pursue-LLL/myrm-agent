import { NextResponse } from 'next/server';

/**
 * 代理 models.dev API 以绕过 CORS 限制
 * GET /api/models-dev
 */
export async function GET() {
  try {
    const response = await fetch('https://models.dev/api.json', {
      headers: {
        Accept: 'application/json',
      },
      signal: AbortSignal.timeout(10_000),
      next: {
        revalidate: 300,
      },
    });

    if (!response.ok) {
      return NextResponse.json({ error: `Failed to fetch: ${response.status}` }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    const isTimeout = error instanceof DOMException && error.name === 'TimeoutError';
    if (!isTimeout) console.error('Failed to proxy models.dev API:', error);

    return NextResponse.json(
      { error: isTimeout ? 'models.dev request timed out' : 'Failed to fetch models data' },
      { status: isTimeout ? 504 : 500 },
    );
  }
}
