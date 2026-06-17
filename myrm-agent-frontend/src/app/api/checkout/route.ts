/**
 * Stripe Checkout proxy — forwards to Control Plane /api/billing/checkout.
 */

import { NextRequest, NextResponse } from 'next/server';
import { isPaidBillingPlan, type PaidBillingPlanKey } from '@/lib/cp-billing';

const CP_API_URL = process.env.MYRM_CP_API_URL || 'http://127.0.0.1:8003';

interface CheckoutRequest {
  plan: PaidBillingPlanKey;
  billingCycle: 'monthly' | 'yearly';
  email?: string;
  enableTrial?: boolean;
}

interface CpCheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: CheckoutRequest = await request.json();
    const { plan, billingCycle, email, enableTrial } = body;

    if (!plan) {
      return NextResponse.json({ error: 'Plan is required' }, { status: 400 });
    }

    if (!isPaidBillingPlan(plan)) {
      return NextResponse.json({ error: 'Invalid plan' }, { status: 400 });
    }

    const authHeader = request.headers.get('Authorization');
    if (!authHeader) {
      return NextResponse.json({ error: 'Authentication required' }, { status: 401 });
    }

    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || request.nextUrl.origin;

    const response = await fetch(`${CP_API_URL}/api/billing/checkout`, {
      method: 'POST',
      headers: {
        Authorization: authHeader,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        plan,
        billing_cycle: billingCycle,
        email,
        enable_trial: enableTrial ?? false,
        success_url: `${baseUrl}/payment/success?session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: `${baseUrl}/payment/cancel`,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('CP checkout error:', response.status, errorText);
      return NextResponse.json({ error: 'Failed to create checkout session' }, { status: response.status });
    }

    const data: CpCheckoutResponse = await response.json();

    return NextResponse.json({
      checkoutUrl: data.checkout_url,
      sessionId: data.session_id,
    });
  } catch (error) {
    console.error('Checkout error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
