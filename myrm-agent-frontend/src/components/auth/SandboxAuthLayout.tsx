/**
 * [INPUT] next-intl::useTranslations (POS: i18n), BrandLogo (POS: 产品品牌标识)
 * [OUTPUT] SandboxAuthLayout: SaaS 认证页分屏壳层（品牌区 + 玻璃表单区）
 * [POS] SaaS 登录/邮箱验证页共享布局，响应式 lg 分屏
 */
'use client';

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import BrandLogo from '@/components/features/app-shell/BrandLogo';
import { cn } from '@/lib/utils';

const FEATURE_KEYS = ['featureAgents', 'featureSync', 'featureSecure'] as const;

interface SandboxAuthLayoutProps {
  children: ReactNode;
  className?: string;
  contentMaxWidth?: string;
}

export default function SandboxAuthLayout({
  children,
  className,
  contentMaxWidth = '420px',
}: SandboxAuthLayoutProps) {
  const t = useTranslations('auth.login');

  return (
    <div className="min-h-screen min-h-[100dvh] bg-background">
      <div className="grid min-h-screen min-h-[100dvh] lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <aside
          className={cn(
            'relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between',
            'border-r border-border/40',
          )}
          aria-hidden
        >
          <div
            className="absolute inset-0 bg-gradient-to-br from-primary/25 via-primary/8 to-background"
            style={{
              backgroundImage: `
                radial-gradient(ellipse 80% 50% at 20% 20%, color-mix(in srgb, var(--primary) 35%, transparent), transparent 55%),
                radial-gradient(ellipse 60% 40% at 80% 80%, color-mix(in srgb, var(--accent-warm, #c4a574) 18%, transparent), transparent 50%)
              `,
            }}
          />
          <div
            className="absolute inset-0 opacity-[0.35]"
            style={{
              backgroundImage:
                'linear-gradient(color-mix(in srgb, var(--foreground) 6%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--foreground) 6%, transparent) 1px, transparent 1px)',
              backgroundSize: '48px 48px',
            }}
          />

          <div className="relative z-10 flex flex-col gap-10 p-10 xl:p-14">
            <div className="flex items-center gap-2">
              <BrandLogo size={56} priority className="w-10 h-10" />
              <span className="text-lg font-semibold brand-gradient-text">MyrmAgent</span>
            </div>
            <div className="space-y-4 max-w-md">
              <h1 className="text-3xl xl:text-4xl font-semibold tracking-tight text-foreground leading-[1.15]">
                {t('brandHeadline')}
              </h1>
              <p className="text-base text-muted-foreground leading-relaxed">{t('brandTagline')}</p>
            </div>
            <ul className="space-y-4">
              {FEATURE_KEYS.map((key) => (
                <li key={key} className="flex gap-3 items-start">
                  <span
                    className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary shadow-[0_0_12px_color-mix(in_srgb,var(--primary)_60%,transparent)]"
                    aria-hidden
                  />
                  <span className="text-sm text-foreground/85 leading-relaxed">{t(key)}</span>
                </li>
              ))}
            </ul>
          </div>

          <p className="relative z-10 px-10 xl:px-14 pb-10 text-xs text-muted-foreground/80">
            {t('brandFooter')}
          </p>
        </aside>

        <main
          className={cn(
            'relative flex flex-col items-center justify-center px-5 py-10 sm:px-8',
            'bg-gradient-to-b from-muted/30 via-background to-background',
            className,
          )}
        >
          <div
            className="pointer-events-none absolute inset-0 opacity-60 dark:opacity-40"
            style={{
              background:
                'radial-gradient(ellipse 70% 45% at 50% 0%, color-mix(in srgb, var(--primary) 12%, transparent), transparent 70%)',
            }}
            aria-hidden
          />

          <div className="relative z-10 w-full space-y-8" style={{ maxWidth: contentMaxWidth }}>
            <div className="flex flex-col items-center gap-3 lg:hidden">
              <BrandLogo size={44} priority />
              <p className="text-center text-sm text-muted-foreground max-w-xs">{t('brandTagline')}</p>
            </div>

            <div
              className={cn(
                'rounded-2xl border border-border/50 p-6 sm:p-8',
                'bg-card/75 backdrop-blur-xl shadow-xl shadow-primary/5',
                'dark:bg-card/60 dark:border-white/10 dark:shadow-black/20',
              )}
            >
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
