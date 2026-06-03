'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { readAuthRedirectParam } from '@/lib/auth-redirect';

/** SaaS signup uses the same Google OAuth entry as login; keep URL for bookmarks and marketing links. */
export default function RegisterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const postAuthPath = readAuthRedirectParam(searchParams) ?? '/';
  const loginHref =
    postAuthPath !== '/' ? `/auth/login?redirect=${encodeURIComponent(postAuthPath)}` : '/auth/login';

  useEffect(() => {
    router.replace(loginHref);
  }, [router, loginHref]);

  return (
    <div className="min-h-screen min-h-[100dvh] flex items-center justify-center bg-background">
      <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" aria-hidden />
    </div>
  );
}
