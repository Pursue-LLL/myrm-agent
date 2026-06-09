import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconPlug, IconDownload } from '@/components/features/icons/PremiumIcons';
import type { MCPRegistryServer } from '@/services/llm-config';

interface MCPRegistryCardProps {
  server: MCPRegistryServer;
  onInstall: (qualifiedName: string) => void;
}

function deriveAuthor(qualifiedName: string): string {
  const parts = qualifiedName.split('/');
  return parts.length > 1 ? parts[0] : '';
}

function formatUseCount(count: number): string {
  if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
  if (count >= 1000) return `${(count / 1000).toFixed(1)}K`;
  return String(count);
}

export const MCPRegistryCard = memo(function MCPRegistryCard({ server, onInstall }: MCPRegistryCardProps) {
  const t = useTranslations('settings');
  const author = deriveAuthor(server.qualifiedName);

  return (
    <div className="flex items-center justify-between p-3 bg-secondary rounded-lg border border-border hover:bg-muted/50 transition-colors group">
      <div className="flex items-center space-x-3 min-w-0 flex-1">
        {server.iconUrl ? (
          <img
            src={server.iconUrl}
            alt=""
            className="w-8 h-8 rounded-md shrink-0 object-contain bg-muted"
          />
        ) : (
          <div className="w-8 h-8 rounded-md shrink-0 bg-primary/10 flex items-center justify-center">
            <IconPlug className="w-4 h-4 text-primary" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground truncate">
            {server.displayName}
          </p>
          {server.description && (
            <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
              {server.description}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1">
            {author && (
              <span className="text-[10px] text-muted-foreground">{author}</span>
            )}
            {server.useCount > 0 && (
              <span className="text-[10px] text-muted-foreground">
                {formatUseCount(server.useCount)} {t('mcpRegistryInstalls')}
              </span>
            )}
          </div>
        </div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onInstall(server.qualifiedName);
        }}
        className="shrink-0 ml-3 flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-xs font-medium"
      >
        <IconDownload className="w-3.5 h-3.5" />
        {t('mcpRegistryInstall')}
      </button>
    </div>
  );
});
