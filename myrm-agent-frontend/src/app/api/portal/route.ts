import { NextRequest, NextResponse } from 'next/server';

const CP_API_URL = process.env.MYRM_CP_API_URL || 'http://127.0.0.1:8003';

interface PortalResponse {
  url: string;
}

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');
    if (!authHeader?.startsWith('Bearer ')) {
      return NextResponse.json({ error: 'Missing or invalid authorization header' }, { status: 401 });
    }

    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || request.nextUrl.origin;

    const response = await fetch(
      `${CP_API_URL}/api/billing/portal?return_url=${encodeURIComponent(`${baseUrl}/subscription`)}`,
      {
        headers: {
          authorization: authHeader,
        },
        cache: 'no-store',
      },
    );

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Failed to create billing portal session: ${errorText}` },
        { status: response.status },
      );
    }

    const data: PortalResponse = await response.json();
    return NextResponse.json({ url: data.url });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Internal server error' },
      { status: 500 },
    );
  }
}
