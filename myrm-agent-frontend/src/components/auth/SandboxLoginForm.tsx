/**
 * [INPUT] OAuthButtons (POS: CP OAuth 跳转), useAuthStore (POS: SaaS JWT 会话)
 * [OUTPUT] SandboxLoginForm: Google OAuth 登录区块
 * [POS] sandbox 构建下 /auth/login 的认证表单
 */
'use client';

import { useTranslations } from 'next-intl';
import OAuthButtons from '@/components/auth/OAuthButtons';

interface SandboxLoginFormProps {
  postAuthPath: string;
}

export default function SandboxLoginForm({ postAuthPath }: SandboxLoginFormProps) {
  const t = useTranslations('auth');

  return (
    <>
      <header className="space-y-1.5 mb-6">
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">{t('login.titleSaas')}</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">{t('login.descriptionOAuthOnly')}</p>
      </header>

      <OAuthButtons redirectPath={postAuthPath} />

      <p className="mt-6 text-center text-[11px] leading-relaxed text-muted-foreground/80">
        {t('login.footerOAuthOnly')}
      </p>
    </>
  );
}
