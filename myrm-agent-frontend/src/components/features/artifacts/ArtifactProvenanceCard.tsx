import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import {
  FileText,
  Code2,
  Table,
  Image as ImageIcon,
  ExternalLink,
  File,
  Download,
  Compass,
  Bot,
  MessageSquare,
} from 'lucide-react';
import type { ArtifactCategory, ArtifactProvenanceItem } from '@/services/artifactProvenance';
import { useRouter } from 'next/navigation';

interface ArtifactProvenanceCardProps {
  item: ArtifactProvenanceItem;
  isSelected?: boolean;
  onToggleSelect?: (id: string) => void;
  onNavigateToSession?: (chatId: string) => void;
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined || bytes === 0) {
    return '0 B';
  }
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export const getCategoryIcon = (category: ArtifactCategory) => {
  switch (category) {
    case 'document':
      return FileText;
    case 'code':
      return Code2;
    case 'data':
      return Table;
    case 'media':
      return ImageIcon;
    case 'link':
      return ExternalLink;
    default:
      return File;
  }
};

const getCategoryColor = (category: ArtifactCategory) => {
  switch (category) {
    case 'document':
      return 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20';
    case 'code':
      return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
    case 'data':
      return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20';
    case 'media':
      return 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20';
    case 'link':
      return 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20';
    default:
      return 'bg-muted text-muted-foreground border-border/40';
  }
};

export const ArtifactProvenanceCard: React.FC<ArtifactProvenanceCardProps> = ({
  item,
  isSelected = false,
  onToggleSelect,
  onNavigateToSession,
}) => {
  const t = useTranslations('artifacts.hub');
  const router = useRouter();
  const IconComponent = getCategoryIcon(item.category);

  const handleNavToSession = () => {
    if (!item.chat_id) {
      return;
    }
    if (onNavigateToSession) {
      onNavigateToSession(item.chat_id);
    } else {
      router.push(`/chat/${item.chat_id}`);
    }
  };

  const handleDownload = () => {
    if (!item.id) {
      return;
    }
    window.open(`/api/v1/files/artifacts/${item.id}/download`, '_blank');
  };

  return (
    <div
      className={cn(
        'group relative flex flex-col justify-between rounded-xl border bg-card p-4 transition-all duration-200',
        'hover:border-primary/40 hover:shadow-sm',
        isSelected ? 'border-primary ring-1 ring-primary/30 bg-primary/5' : 'border-border/60',
      )}
    >
      <div>
        <div className="flex items-start justify-between gap-3 mb-2.5">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className={cn('p-2 rounded-lg border shrink-0', getCategoryColor(item.category))}>
              <IconComponent className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <h4 className="font-semibold text-sm text-foreground truncate" title={item.name}>
                {item.name}
              </h4>
              <p className="text-[11px] text-muted-foreground">
                {formatBytes(item.size_bytes)} · {new Date(item.updated_at).toLocaleDateString()}
              </p>
            </div>
          </div>

          {onToggleSelect && (
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => onToggleSelect(item.id)}
              className="mt-1 h-4 w-4 rounded border-border text-primary focus:ring-primary cursor-pointer"
            />
          )}
        </div>

        {item.description && (
          <p className="text-xs text-muted-foreground line-clamp-2 mb-3 leading-relaxed">
            {item.description}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {item.chat_title && (
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] bg-muted/60 text-muted-foreground border border-border/40 max-w-[200px] truncate"
              title={`${t('originSession')}: ${item.chat_title}`}
            >
              <MessageSquare className="w-3 h-3 shrink-0" />
              <span className="truncate">{item.chat_title}</span>
            </span>
          )}

          {item.agent_id && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] bg-muted/60 text-muted-foreground border border-border/40">
              <Bot className="w-3 h-3 shrink-0" />
              <span>{item.agent_id}</span>
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 pt-2.5 border-t border-border/40">
        {item.chat_id ? (
          <button
            type="button"
            onClick={handleNavToSession}
            className={cn(
              'inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium',
              'text-primary hover:text-primary/90 bg-primary/10 hover:bg-primary/15',
              'transition-colors duration-150',
            )}
            title={t('navToSession')}
          >
            <Compass className="w-3.5 h-3.5" />
            <span>{t('navToSession')}</span>
          </button>
        ) : (
          <div />
        )}

        <button
          type="button"
          onClick={handleDownload}
          className="inline-flex items-center gap-1 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          title={t('download')}
        >
          <Download className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
