'use client';

/**
 * [INPUT]
 * @/services/kanban::listBoards (POS: Kanban API 客户端)
 * @/services/cron::listCronJobs (POS: Cron API 客户端)
 *
 * [OUTPUT]
 * ProjectsDashboard: Projects 模式聚合仪表盘（Kanban/Cron/Artifacts 入口卡片 + 轻量统计）
 *
 * [POS]
 * `/projects` 路由业务 UI。页面壳在 `src/app/projects/page.tsx`，本组件负责卡片网格与并行统计拉取。
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { FolderKanban, Clock, FileText, ArrowRight } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import { listBoards } from '@/services/kanban';
import { listCronJobs } from '@/services/cron';
import type { ComponentType } from 'react';

interface ProjectStats {
  kanbanBoards: number | null;
  cronJobs: number | null;
}

interface ProjectEntry {
  id: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  href: string;
  titleKey: string;
  descKey: string;
  statKey?: keyof ProjectStats;
  statLabelKey?: string;
}

const PROJECT_ENTRIES: ProjectEntry[] = [
  {
    id: 'kanban',
    icon: FolderKanban,
    href: '/settings/kanban',
    titleKey: 'kanban.title',
    descKey: 'kanban.desc',
    statKey: 'kanbanBoards',
    statLabelKey: 'kanban.statLabel',
  },
  {
    id: 'cron',
    icon: Clock,
    href: '/settings/cron',
    titleKey: 'cron.title',
    descKey: 'cron.desc',
    statKey: 'cronJobs',
    statLabelKey: 'cron.statLabel',
  },
  {
    id: 'artifacts',
    icon: FileText,
    href: '/artifacts',
    titleKey: 'artifacts.title',
    descKey: 'artifacts.desc',
  },
];

function useProjectStats(): ProjectStats {
  const [stats, setStats] = useState<ProjectStats>({ kanbanBoards: null, cronJobs: null });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [boardsRes, cronRes] = await Promise.allSettled([
        listBoards(),
        listCronJobs({ limit: 1 }),
      ]);

      if (cancelled) return;

      setStats({
        kanbanBoards: boardsRes.status === 'fulfilled' ? boardsRes.value.total : null,
        cronJobs: cronRes.status === 'fulfilled' ? cronRes.value.total : null,
      });
    }

    load();
    return () => { cancelled = true; };
  }, []);

  return stats;
}

export default function ProjectsDashboard() {
  const router = useRouter();
  const t = useTranslations('projects');
  const stats = useProjectStats();

  const renderStat = (entry: ProjectEntry) => {
    if (!entry.statKey || !entry.statLabelKey) return null;
    const count = stats[entry.statKey];
    if (count === null) return null;
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="text-2xl font-semibold text-foreground">{count}</span>
        <span className="text-muted-foreground">{t(entry.statLabelKey)}</span>
      </div>
    );
  };

  return (
    <div className="min-h-[calc(100vh-2rem)] w-full max-w-5xl mx-auto p-6 md:p-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {PROJECT_ENTRIES.map((entry) => {
          const Icon = entry.icon;
          return (
            <Card
              key={entry.id}
              className={cn(
                'group cursor-pointer transition-all duration-200',
                'hover:border-primary/30 hover:shadow-md hover:shadow-primary/5',
              )}
              onClick={() => router.push(entry.href)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between mb-3">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Icon size={20} className="text-primary" />
                  </div>
                  <ArrowRight
                    size={16}
                    className="text-muted-foreground opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
                  />
                </div>
                <CardTitle className="text-base">{t(entry.titleKey)}</CardTitle>
                <CardDescription>{t(entry.descKey)}</CardDescription>
              </CardHeader>
              <CardContent className="pt-2">
                {renderStat(entry)}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
