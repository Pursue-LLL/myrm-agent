import { toast } from 'sonner';
import type { OrgMCPDelivery } from '@/services/enterprise-org';

export function showOrgMcpDeliveryToast(
  t: (key: string, values?: Record<string, string | number>) => string,
  delivery: OrgMCPDelivery,
) {
  const message = t('mcpDeliverySummary', {
    synced: delivery.synced,
    skipped: delivery.skipped,
    failed: delivery.failed,
  });
  if (delivery.failed > 0) {
    toast.error(message);
    return;
  }
  toast.success(message);
}
