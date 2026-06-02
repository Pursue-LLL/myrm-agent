/**
 * Top-up WU proxy — forwards to Control Plane /api/billing/topup.
 */

import { NextRequest, NextResponse } from 'next/server';

const CP_API_URL = process.env.MYRM_CP_API_URL || 'http://127.0.0.1:8003';

interface TopupRequest {
  amount_usd: number;
}

interface CpTopupResponse {
  checkout_url: string;
  session_id: string;
  wu_amount: number;
}

export async function POST(request: NextRequest) {
  try {
    const body: TopupRequest = await request.json();
    const { amount_usd } = body;

    if (!amount_usd || amount_usd < 1 || amount_usd > 100) {
      return NextResponse.json({ error: 'amount_usd must be between 1 and 100' }, { status: 400 });
    }

    const authHeader = request.headers.get('Authorization');
    if (!authHeader) {
      return NextResponse.json({ error: 'Authentication required' }, { status: 401 });
    }

    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || request.nextUrl.origin;

    const response = await fetch(`${CP_API_URL}/api/billing/topup`, {
      method: 'POST',
      headers: {
        Authorization: authHeader,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        amount_usd,
        success_url: `${baseUrl}/payment/success?type=topup&session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: `${baseUrl}/payment/cancel`,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('CP topup error:', response.status, errorText);
      return NextResponse.json({ error: 'Failed to create top-up session' }, { status: response.status });
    }

    const data: CpTopupResponse = await response.json();

    return NextResponse.json({
      checkoutUrl: data.checkout_url,
      sessionId: data.session_id,
      wuAmount: data.wu_amount,
    });
  } catch (error) {
    console.error('Topup error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
