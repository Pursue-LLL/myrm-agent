import { useTranslations } from 'next-intl';
import type { ConnectionStatus } from './ConnectionBadge';

const STATUS_KEY: Record<ConnectionStatus, string> = {
  unchecked: 'connStatusUnchecked',
  checking: 'connStatusChecking',
  connected: 'connStatusConnected',
  error: 'connStatusError',
  unconfigured: 'connStatusUnconfigured',
};

export function useConnectionStatusLabel(status: ConnectionStatus): string {
  const t = useTranslations('channels');
  return t(STATUS_KEY[status]);
}
