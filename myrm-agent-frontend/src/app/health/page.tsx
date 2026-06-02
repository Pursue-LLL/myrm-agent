/**
 * [INPUT]
 * - src/components/ui/health/DoctorDashboard.tsx::DoctorDashboard (POS: 系统诊断看板主组件)
 *
 * [OUTPUT]
 * - HealthPage: 系统诊断的 Next.js 独立路由页面。
 *
 * [POS]
 * 页面级入口组件。提供独立的 /health 路由访问健康诊断面板体系。
 */
import { getTranslations } from 'next-intl/server';
import { DoctorDashboard } from '@/components/ui/health/DoctorDashboard';

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'health' });
  return {
    title: `${t('title')} - MyrmAgent`,
  };
}

export default async function HealthPage(props: { params: Promise<{ locale: string }> }) {
  const { locale } = await props.params;
  const t = await getTranslations({ locale, namespace: 'health' });

  return (
    <div className="flex h-full w-full flex-col p-4 md:p-8 bg-zinc-950/50">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <header className="mb-6 flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-zinc-100 flex items-center gap-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="w-6 h-6 text-indigo-400"
              >
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </svg>
              {t('title')}
            </h1>
            <p className="text-sm text-zinc-400">{t('overview')}</p>
          </div>
        </header>

        <DoctorDashboard />
      </div>
    </div>
  );
}
