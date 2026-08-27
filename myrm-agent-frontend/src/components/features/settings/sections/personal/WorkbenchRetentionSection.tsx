'use client';

import { memo } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import {
  Brain,
  BookOpen,
  Wand2,
  Code,
  Timer,
  HardDrive,
  ShieldCheck,
  Download,
  ArrowRight,
  RefreshCw,
  Layers,
  Sparkles,
  Server,
  Laptop,
  Cloud,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useWorkbenchRetentionSummary, type WorkbenchRetentionSummary } from './useWorkbenchRetentionSummary';
import { SettingsSkeleton } from '../../common/SettingsSkeleton';
import { Button } from '@/components/primitives/button';

interface AssetMetricCardProps {
  icon: React.ReactNode;
  title: string;
  count: number | string;
  subValue: string;
  description: string;
  href: string;
  status: 'ok' | 'unavailable';
  accentColorClass: string;
}

const AssetMetricCard = memo<AssetMetricCardProps>(
  ({ icon, title, count, subValue, description, href, status, accentColorClass }) => {
    return (
      <Link
        href={href}
        className="group relative flex flex-col justify-between overflow-hidden rounded-2xl border border-border/60 bg-background/50 p-5 backdrop-blur-xl transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-accent/20 hover:shadow-xl dark:bg-card/40"
      >
        <div className="absolute right-0 top-0 -mr-6 -mt-6 h-24 w-24 rounded-full bg-primary/5 blur-2xl transition-all duration-500 group-hover:bg-primary/10" />

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className={cn('flex h-10 w-10 items-center justify-center rounded-xl border', accentColorClass)}>
              {icon}
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors group-hover:text-foreground">
              <span className="font-medium">{subValue}</span>
              <ArrowRight className="h-3.5 w-3.5 opacity-0 transition-all duration-300 group-hover:translate-x-0.5 group-hover:opacity-100" />
            </div>
          </div>

          <div>
            <div className="text-2xl font-black tracking-tight text-foreground">
              {status === 'unavailable' ? '—' : count}
            </div>
            <h3 className="text-sm font-bold text-foreground/90">{title}</h3>
          </div>

          <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">{description}</p>
        </div>
      </Link>
    );
  },
);
AssetMetricCard.displayName = 'AssetMetricCard';

function formatBytes(bytes: number): string {
  if (bytes === 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / 1024 ** i).toFixed(1)} ${units[i]}`;
}

const WorkbenchRetentionSection = memo(() => {
  const t = useTranslations('settings.workbench');
  const { summary, loading, reload } = useWorkbenchRetentionSummary();

  if (loading && !summary) {
    return <SettingsSkeleton />;
  }

  const data: WorkbenchRetentionSummary = summary ?? {
    wikiConcepts: 0,
    wikiArticles: 0,
    wikiRawFiles: 0,
    wikiStatus: 'unavailable',
    totalMemories: 0,
    memoryHealthScore: 100,
    memoryStatus: 'unavailable',
    totalSkills: 0,
    totalEvolutions: 0,
    skillsStatus: 'unavailable',
    totalRules: 0,
    totalRuleChars: 0,
    workspaceRoot: '',
    rulesStatus: 'unavailable',
    cronJobsCount: 0,
    cronExecutions: 0,
    cronStatus: 'unavailable',
    storageDataDir: '',
    storageUsedBytes: 0,
    storageTotalBytes: 0,
    storageFreeBytes: 0,
    storageStatus: 'unavailable',
    deployMode: 'local',
    isLocal: true,
    isTauri: false,
    isSandboxEnv: false,
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-3xl border border-border/60 bg-gradient-to-br from-primary/10 via-background to-secondary/30 p-6 sm:p-8 backdrop-blur-2xl">
        <div className="absolute right-0 top-0 -mr-16 -mt-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 relative z-10">
          <div className="space-y-2 max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              <Sparkles className="h-3.5 w-3.5" />
              {t('badge')}
            </div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-foreground">{t('title')}</h1>
            <p className="text-sm text-muted-foreground leading-relaxed">{t('description')}</p>
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={reload}
              className="gap-1.5 rounded-xl border-border/60 hover:bg-accent/40"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
              <span>{t('refresh')}</span>
            </Button>
          </div>
        </div>
      </div>

      {/* Asset KPI Matrix Grid */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-black uppercase tracking-wider text-muted-foreground/80 flex items-center gap-2">
            <Layers className="h-4 w-4 text-primary" />
            {t('assetMatrixTitle')}
          </h2>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* 1. Memory Vault */}
          <AssetMetricCard
            icon={<Brain className="h-5 w-5 text-indigo-500" />}
            title={t('assets.memory.title')}
            count={data.totalMemories}
            subValue={t('assets.memory.score', { score: data.memoryHealthScore })}
            description={t('assets.memory.desc')}
            href="/settings/memory"
            status={data.memoryStatus}
            accentColorClass="bg-indigo-500/10 border-indigo-500/20 text-indigo-500"
          />

          {/* 2. Wiki Knowledge Vault */}
          <AssetMetricCard
            icon={<BookOpen className="h-5 w-5 text-emerald-500" />}
            title={t('assets.wiki.title')}
            count={data.wikiConcepts}
            subValue={t('assets.wiki.rawCount', { count: data.wikiRawFiles })}
            description={t('assets.wiki.desc')}
            href="/settings/wiki"
            status={data.wikiStatus}
            accentColorClass="bg-emerald-500/10 border-emerald-500/20 text-emerald-500"
          />

          {/* 3. Skills Library */}
          <AssetMetricCard
            icon={<Wand2 className="h-5 w-5 text-amber-500" />}
            title={t('assets.skills.title')}
            count={data.totalSkills}
            subValue={t('assets.skills.evolutions', { count: data.totalEvolutions })}
            description={t('assets.skills.desc')}
            href="/settings/skills"
            status={data.skillsStatus}
            accentColorClass="bg-amber-500/10 border-amber-500/20 text-amber-500"
          />

          {/* 4. Workspace Rules */}
          <AssetMetricCard
            icon={<Code className="h-5 w-5 text-cyan-500" />}
            title={t('assets.rules.title')}
            count={data.totalRules}
            subValue={t('assets.rules.chars', { count: data.totalRuleChars.toLocaleString() })}
            description={t('assets.rules.desc')}
            href="/settings/workspaceRules"
            status={data.rulesStatus}
            accentColorClass="bg-cyan-500/10 border-cyan-500/20 text-cyan-500"
          />

          {/* 5. Cron Automation Workflows */}
          <AssetMetricCard
            icon={<Timer className="h-5 w-5 text-violet-500" />}
            title={t('assets.cron.title')}
            count={data.cronJobsCount}
            subValue={t('assets.cron.runs', { count: data.cronExecutions })}
            description={t('assets.cron.desc')}
            href="/settings/cron"
            status={data.cronStatus}
            accentColorClass="bg-violet-500/10 border-violet-500/20 text-violet-500"
          />

          {/* 6. Persistent Storage & Volume */}
          <AssetMetricCard
            icon={<HardDrive className="h-5 w-5 text-rose-500" />}
            title={t('assets.storage.title')}
            count={data.storageStatus === 'ok' ? formatBytes(data.storageUsedBytes) : '—'}
            subValue={data.storageStatus === 'ok' ? `${formatBytes(data.storageFreeBytes)} free` : ''}
            description={t('assets.storage.desc')}
            href="/settings/system"
            status={data.storageStatus}
            accentColorClass="bg-rose-500/10 border-rose-500/20 text-rose-500"
          />
        </div>
      </section>

      {/* Neutral Platform Advantage & Data Sovereignty */}
      <section className="rounded-3xl border border-border/60 bg-gradient-to-r from-secondary/40 via-background to-secondary/20 p-6 sm:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-500" />
              {t('sovereignty.title')}
            </h2>
            <p className="text-sm text-muted-foreground leading-relaxed">{t('sovereignty.subtitle')}</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant="outline" size="sm" className="gap-1.5 rounded-xl border-border/60">
              <Link href="/settings/developer?sub=importExport">
                <Download className="h-3.5 w-3.5" />
                {t('sovereignty.exportConfig')}
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="gap-1.5 rounded-xl border-border/60">
              <Link href="/settings/memory?sub=backup">
                <Brain className="h-3.5 w-3.5" />
                {t('sovereignty.exportMemory')}
              </Link>
            </Button>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-border/50 bg-background/60 p-4 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">{t('sovereignty.points.decouplingTitle')}</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">{t('sovereignty.points.decouplingDesc')}</p>
          </div>
          <div className="rounded-2xl border border-border/50 bg-background/60 p-4 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">{t('sovereignty.points.standardTitle')}</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">{t('sovereignty.points.standardDesc')}</p>
          </div>
          <div className="rounded-2xl border border-border/50 bg-background/60 p-4 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">{t('sovereignty.points.zeroLockinTitle')}</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">{t('sovereignty.points.zeroLockinDesc')}</p>
          </div>
        </div>
      </section>

      {/* Deployment Modes Honest Storage Copy */}
      <section className="rounded-3xl border border-border/60 bg-card/30 p-6 sm:p-8 space-y-6">
        <div className="space-y-1">
          <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
            {data.isTauri ? (
              <Laptop className="h-5 w-5 text-primary" />
            ) : data.isSandboxEnv ? (
              <Cloud className="h-5 w-5 text-primary" />
            ) : (
              <Server className="h-5 w-5 text-primary" />
            )}
            {t('deployHonest.title')}
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {data.isTauri
              ? t('deployHonest.tauriSubtitle')
              : data.isSandboxEnv
                ? t('deployHonest.sandboxSubtitle')
                : t('deployHonest.localSubtitle')}
          </p>
        </div>

        <div className="rounded-2xl border border-border/50 bg-muted/20 p-4 sm:p-5 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
            <span className="font-semibold text-foreground">{t('deployHonest.dataPathLabel')}:</span>
            <code className="font-mono bg-muted/60 px-2 py-1 rounded-md text-foreground/90 break-all">
              {data.storageDataDir || (data.isLocal ? '~/.myrm' : '/workspace/data')}
            </code>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {data.isTauri
              ? t('deployHonest.tauriDetail')
              : data.isSandboxEnv
                ? t('deployHonest.sandboxDetail')
                : t('deployHonest.localDetail')}
          </p>
        </div>
      </section>
    </div>
  );
});

WorkbenchRetentionSection.displayName = 'WorkbenchRetentionSection';

export default WorkbenchRetentionSection;
