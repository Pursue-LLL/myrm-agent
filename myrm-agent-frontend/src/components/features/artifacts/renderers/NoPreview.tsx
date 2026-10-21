'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Download } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Artifact, ArtifactType } from '@/store/chat/types';
import { getArtifactIcon } from '../artifactUtils';

interface NoPreviewProps {
  artifact: Artifact;
  onDownload: () => void;
}

/** 无法预览组件 */
const NoPreview: React.FC<NoPreviewProps> = memo(({ artifact, onDownload }) => {
  const t = useTranslations('artifacts');
  const Icon = getArtifactIcon(artifact.type as ArtifactType, artifact.filename);

  return (
    <div className="h-full flex flex-col items-center justify-center gap-4 text-center p-8">
      <div className="w-20 h-20 rounded-2xl bg-muted flex items-center justify-center">
        <Icon className="w-10 h-10 text-muted-foreground" />
      </div>
      <div>
        <h3 className="text-lg font-medium text-foreground">{artifact.filename}</h3>
        <p className="text-sm text-muted-foreground mt-1">{t('noPreview')}</p>
        <p className="text-xs text-muted-foreground/70 mt-2">{t('downloadHint')}</p>
      </div>
      <Button onClick={onDownload} className="mt-2">
        <Download className="w-4 h-4 mr-2" />
        {t('download')}
      </Button>
    </div>
  );
});
NoPreview.displayName = 'NoPreview';

export default NoPreview;
