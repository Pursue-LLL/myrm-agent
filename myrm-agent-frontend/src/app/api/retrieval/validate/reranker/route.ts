/**
 * [INPUT]
 * - @/lib/server/postJsonHttp::postJsonHttp (POS: Server-side JSON POST transport helper)
 *
 * [OUTPUT]
 * - POST: Validate reranker retrieval config against the FastAPI backend.
 *
 * [POS]
 * Reranker retrieval validation proxy. Bridges the settings UI to the backend
 * validation endpoint without routing the request back through Next.js fetch.
 */
import { NextRequest, NextResponse } from 'next/server';
import { postJsonHttp } from '@/lib/server/postJsonHttp';

export const runtime = 'nodejs';

export async function POST(request: NextRequest) {
  try {
    const body: unknown = await request.json();

    const apiHost = process.env.API_HOST || '127.0.0.1';
    const apiPort = process.env.API_PORT || '25808';
    const { status, text } = await postJsonHttp(`http://${apiHost}:${apiPort}/api/v1/retrieval/reranker`, body);
    try {
      const data = text ? JSON.parse(text) : {};
      return NextResponse.json(data, { status });
    } catch {
      return NextResponse.json(
        {
          success: false,
          message: 'Backend returned non-JSON body',
          error: text.slice(0, 800),
        },
        { status: 502 },
      );
    }
  } catch (error) {
    console.error('Reranker validation proxy error:', error);
    return NextResponse.json({ success: false, message: 'Proxy error', error: String(error) }, { status: 500 });
  }
}
