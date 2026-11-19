'use client';

/**
 * [INPUT]
 * - ./ArtifactCard (POS: Chat card of one artifact)
 * - ./SkillDetectionCard (POS: Prompt to save a skill detected in the artifacts)
 * - @/store/useArtifactPortalStore (POS: Full-screen artifact preview)
 *
 * [OUTPUT]
 * - ArtifactsDisplay: The file artifacts of one assistant message as a titled grid of cards.
 *
 * [POS]
 * Artifact list of a message. Generated images are not artifacts: the media tool that made one registers it, and the
 * generated-media cards show it.
 */

import React, { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Artifact } from '@/store/chat/types';
import { Package } from 'lucide-react';
import ArtifactCard from './ArtifactCard';
import SkillDetectionCard from './SkillDetectionCard';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';

interface ArtifactsDisplayProps {
  artifacts: Artifact[];
  chatId?: string;
  className?: string;
}

const ArtifactsDisplay: React.FC<ArtifactsDisplayProps> = ({ artifacts, chatId, className }) => {
  const t = useTranslations('artifacts');
  const openArtifact = useArtifactPortalStore((state) => state.openArtifact);

  const handlePreview = useCallback(
    (artifact: Artifact) => {
      openArtifact(artifact);
    },
    [openArtifact],
  );

  if (!artifacts || artifacts.length === 0) {
    return null;
  }

  return (
    <div className={cn('flex flex-col space-y-3', className)}>
      <div className="flex items-center gap-2">
        <Package className="w-5 h-5 text-muted-foreground" />
        <h3 className="text-sm font-medium text-foreground">{t('title')}</h3>
        <span className="text-xs text-muted-foreground px-1.5 py-0.5 bg-muted rounded-full">{artifacts.length}</span>
      </div>

      {chatId && <SkillDetectionCard artifacts={artifacts} chatId={chatId} />}

      <div className="grid gap-2 sm:grid-cols-2">
        {artifacts.map((artifact) => (
          <ArtifactCard key={artifact.id} artifact={artifact} onPreview={handlePreview} />
        ))}
      </div>
    </div>
  );
};

export default ArtifactsDisplay;
