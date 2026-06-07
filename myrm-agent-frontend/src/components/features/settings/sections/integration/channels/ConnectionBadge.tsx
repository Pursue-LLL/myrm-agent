'use client';

import { IconLoader, IconWifi, IconWifiOff, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

export type ConnectionStatus = 'unchecked' | 'checking' | 'connected' | 'error' | 'unconfigured';

const STATUS_CONFIG: Record<ConnectionStatus, { icon: React.ReactNode; className: string }> = {
  unchecked: {
    icon: <IconAlertCircle className="h-3.5 w-3.5" />,
    className: 'bg-muted text-muted-foreground border-muted',
  },
  checking: {
    icon: <IconLoader className="h-3.5 w-3.5 animate-spin" />,
    className: 'bg-muted text-muted-foreground border-muted',
  },
  connected: {
    icon: <IconWifi className="h-3.5 w-3.5" />,
    className: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20',
  },
  error: {
    icon: <IconWifiOff className="h-3.5 w-3.5" />,
    className: 'bg-destructive/10 text-destructive border-destructive/20',
  },
  unconfigured: {
    icon: <IconAlertCircle className="h-3.5 w-3.5" />,
    className: 'bg-muted text-muted-foreground border-muted',
  },
};

export function ConnectionBadge({ status, label }: { status: ConnectionStatus; label: string }) {
  const c = STATUS_CONFIG[status];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
        c.className,
      )}
    >
      {c.icon}
      {label}
    </span>
  );
}
