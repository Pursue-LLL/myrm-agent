'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Zap, Upload, Search, Package, FolderOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';

type EmptyStateType = 'market' | 'personal' | 'local' | 'enabled' | 'search';

interface SkillEmptyStateProps {
  type: EmptyStateType;
  onUpload?: () => void;
}

const SkillEmptyState = memo(({ type, onUpload }: SkillEmptyStateProps) => {
  const t = useTranslations('settings.skills');

  const configs: Record<
    EmptyStateType,
    {
      icon: React.ElementType;
      title: string;
      description: string;
      showUploadButton: boolean;
    }
  > = {
    market: {
      icon: Package,
      title: t('market.empty'),
      description: t('market.emptyDesc'),
      showUploadButton: false,
    },
    personal: {
      icon: Upload,
      title: t('personal.empty'),
      description: t('personal.emptyDesc'),
      showUploadButton: true,
    },
    local: {
      icon: FolderOpen,
      title: t('local.empty'),
      description: t('local.emptyDesc'),
      showUploadButton: false,
    },
    enabled: {
      icon: Zap,
      title: t('enabled.empty'),
      description: t('enabled.emptyDesc'),
      showUploadButton: false,
    },
    search: {
      icon: Search,
      title: t('search.empty'),
      description: t('search.emptyDesc'),
      showUploadButton: false,
    },
  };

  const config = configs[type];
  const Icon = config.icon;

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
        <Icon size={28} className="text-muted-foreground" />
      </div>
      <h3 className="text-lg font-medium text-foreground mb-2">{config.title}</h3>
      <p className="text-sm text-muted-foreground max-w-md mb-6">{config.description}</p>
      {config.showUploadButton && onUpload && (
        <Button onClick={onUpload} className="gap-2">
          <Upload size={16} />
          {t('personal.uploadButton')}
        </Button>
      )}
    </div>
  );
});

SkillEmptyState.displayName = 'SkillEmptyState';

export default SkillEmptyState;
