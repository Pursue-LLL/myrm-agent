import { NextResponse } from 'next/server';

export async function POST() {
  // Debug log endpoint - 仅用于开发环境
  return NextResponse.json({ success: true });
}
