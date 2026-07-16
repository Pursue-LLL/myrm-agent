'use client';

import { lazy, memo, Suspense, useState } from 'react';
import { useTranslations } from 'next-intl';
import { BarChart3, Cpu, Shield, ShieldAlert } from 'lucide-react';

const EnterpriseMembersTab = lazy(() => import('./EnterpriseMembersTab'));
const EnterpriseAuditTab = lazy(() => import('./EnterpriseAuditTab'));
const EnterpriseUsageTab = lazy(() => import('./EnterpriseUsageTab'));
const EnterpriseModelPolicyTab = lazy(() => import('./EnterpriseModelPolicyTab'));

type EnterpriseTab = 'members' | 'usage' | 'audit' | 'model-policy';

const TAB_FALLBACK = <div className="animate-pulse h-48 bg-muted rounded" />;

const EnterpriseOrgSection = memo(() => {
  const t = useTranslations('settings.enterprise');
  const [activeTab, setActiveTab] = useState<EnterpriseTab>('members');

  const tabs = [
    { key: 'members' as const, icon: Shield, label: t('membersTab') },
    { key: 'model-policy' as const, icon: Cpu, label: t('modelPolicyTab', { default: 'Model Policy' }) },
    { key: 'usage' as const, icon: BarChart3, label: t('usageTab') },
    { key: 'audit' as const, icon: ShieldAlert, label: t('auditTab') },
  ];

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <nav className="flex gap-1 rounded-lg bg-muted/50 p-1 border border-border/40 overflow-x-auto">
        {tabs.map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${
              activeTab === key
                ? 'bg-background shadow-sm text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </nav>

      {/* Tab Content */}
      <Suspense fallback={TAB_FALLBACK}>
        {activeTab === 'members' && <EnterpriseMembersTab />}
        {activeTab === 'model-policy' && <EnterpriseModelPolicyTab />}
        {activeTab === 'usage' && <EnterpriseUsageTab />}
        {activeTab === 'audit' && <EnterpriseAuditTab />}
      </Suspense>
    </div>
  );
});

EnterpriseOrgSection.displayName = 'EnterpriseOrgSection';

export default EnterpriseOrgSection;
