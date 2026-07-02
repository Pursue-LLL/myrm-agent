'use client';

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { isSandbox } from '@/lib/deploy-mode';
import { getMyOrg } from '@/services/enterprise-org';
import { publishToMarketplace } from '@/services/marketplace';
import { cn } from '@/lib/utils/classnameUtils';
import { Upload, Loader2, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

interface PublishToOrgButtonProps {
  agentId: string;
  agentName: string;
  className?: string;
}

const PublishToOrgButton = ({ agentId, agentName, className }: PublishToOrgButtonProps) => {
  const t = useTranslations('agent.configPanel');
  const [publishing, setPublishing] = useState(false);
  const [published, setPublished] = useState(false);

  const handlePublish = useCallback(async () => {
    if (publishing || published) return;
    setPublishing(true);
    try {
      const org = await getMyOrg();

      const exportRes = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/marketplace-export`, {
        headers: getAuthHeaders(),
      });
      if (!exportRes.ok) throw new Error(`Export failed: ${exportRes.status}`);
      const { data: packageData } = await exportRes.json();

      await publishToMarketplace({
        org_id: org.id,
        name: agentName,
        description: packageData.agent_profile?.description || '',
        avatar: packageData.agent_profile?.avatar_url || null,
        tags: [],
        profile_data: packageData,
      });

      setPublished(true);
      toast.success(t('publishSuccess') || `Published "${agentName}" to org marketplace`);
    } catch (e) {
      console.error(e);
      toast.error(t('publishError') || 'Failed to publish to org marketplace');
    } finally {
      setPublishing(false);
    }
  }, [agentId, agentName, publishing, published, t]);

  if (!isSandbox()) return null;

  return (
    <button
      onClick={handlePublish}
      disabled={publishing || published}
      className={cn(
        'w-full py-2 px-4 rounded-lg',
        'flex items-center justify-center gap-2',
        'text-xs font-medium transition-all duration-200',
        'border border-dashed border-border/40',
        'text-muted-foreground hover:text-foreground',
        'hover:border-primary/40 hover:bg-primary/5',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        published && 'border-green-500/30 text-green-600 bg-green-500/5',
        className,
      )}
    >
      {publishing ? (
        <Loader2 size={12} className="animate-spin" />
      ) : published ? (
        <CheckCircle size={12} className="text-green-500" />
      ) : (
        <Upload size={12} />
      )}
      <span>
        {published
          ? (t('publishedToOrg') || 'Published to Org')
          : (t('publishToOrg') || 'Publish to Org')}
      </span>
    </button>
  );
};

export default memo(PublishToOrgButton);
