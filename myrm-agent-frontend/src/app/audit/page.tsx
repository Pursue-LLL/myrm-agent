'use client';

import { useState } from 'react';
import { useLocale } from 'next-intl';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import AuditLogTable from './components/AuditLogTable';
import StatsDashboard from './components/StatsDashboard';
import { localizeReactNode } from '@/lib/utils/localeText';

type AuditTab = 'logs' | 'stats';

const AuditPage = () => {
  const locale = useLocale();
  const [activeTab, setActiveTab] = useState<AuditTab>('logs');

  return localizeReactNode(
    <div className="container mx-auto h-full py-6 px-4 md:px-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Bash Command Audit / Bash命令审计</h1>
        <p className="text-muted-foreground mt-2">
          View bash command execution logs and statistics / 查看bash命令执行日志和统计
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as AuditTab)}>
        <TabsList className="grid w-full max-w-md grid-cols-2 h-auto">
          <TabsTrigger key="logs" value="logs" className="min-w-0">
            <span className="truncate">Audit Logs / 审计日志</span>
          </TabsTrigger>
          <TabsTrigger key="stats" value="stats" className="min-w-0">
            <span className="truncate">Statistics / 统计</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="logs" className="mt-6">
          <AuditLogTable />
        </TabsContent>

        <TabsContent value="stats" className="mt-6">
          <StatsDashboard />
        </TabsContent>
      </Tabs>
    </div>,
    locale,
  );
};

export default AuditPage;
