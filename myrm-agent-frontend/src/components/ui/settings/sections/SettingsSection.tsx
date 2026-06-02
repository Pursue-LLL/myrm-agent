'use client';

import { memo, ReactNode } from 'react';

interface SettingsSectionProps {
  title: string | ReactNode;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}

const SettingsSection = memo<SettingsSectionProps>(({ title, description, action, children }) => (
  <div className="flex flex-col space-y-6 p-6 lg:p-8 bg-secondary/30 dark:bg-secondary/20 rounded-2xl border border-border/50">
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-2">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        {description && <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
    <div className="space-y-6">{children}</div>
  </div>
));

SettingsSection.displayName = 'SettingsSection';

export default SettingsSection;
