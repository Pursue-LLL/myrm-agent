'use client';

import React, { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Artifact } from '@/store/chat/types';
import { Package } from 'lucide-react';
import ArtifactCard from './ArtifactCard';
import SkillDetectionCard from './SkillDetectionCard';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import useChatStore from '@/store/useChatStore';
import { ImageResultCard } from '@/components/ui/image-gen/ImageResultCard';
import { getStorageUrl } from '@/lib/api';

function isGeneratedImage(artifact: Artifact): boolean {
  return artifact.type === 'image' && artifact.filename.startsWith('generated_') && !!artifact.preview_url;
}

interface ArtifactsDisplayProps {
  artifacts: Artifact[];
  chatId?: string;
  className?: string;
}

const ArtifactsDisplay: React.FC<ArtifactsDisplayProps> = ({ artifacts, chatId, className }) => {
  const t = useTranslations('artifacts');
  const tImageGen = useTranslations('imageGen');
  const openArtifact = useArtifactPortalStore((state) => state.openArtifact);
  const setInputMessage = useChatStore((state) => state.setInputMessage);

  const handlePreview = useCallback(
    (artifact: Artifact) => {
      openArtifact(artifact);
    },
    [openArtifact],
  );

  const handleEditRequest = useCallback(
    (_imageUrl: string) => {
      setInputMessage(tImageGen('editPromptPrefix'));
    },
    [setInputMessage, tImageGen],
  );

  if (!artifacts || artifacts.length === 0) {
    return null;
  }

  const imageArtifacts = artifacts.filter(isGeneratedImage);
  const otherArtifacts = artifacts.filter((a) => !isGeneratedImage(a));

  return (
    <div className={cn('flex flex-col space-y-3', className)}>
      {/* Generated images rendered as rich cards */}
      {imageArtifacts.length > 0 && (
        <ImageResultCard
          images={imageArtifacts.map((a) => ({
            url: getStorageUrl(a.preview_url),
            mimeType: a.content_type,
          }))}
          model={imageArtifacts[0].filename.replace(/^generated_|\.png$/g, '')}
          onEditRequest={handleEditRequest}
        />
      )}

      {/* Other artifacts */}
      {otherArtifacts.length > 0 && (
        <>
          <div className="flex items-center gap-2">
            <Package className="w-5 h-5 text-muted-foreground" />
            <h3 className="text-sm font-medium text-foreground">{t('title')}</h3>
            <span className="text-xs text-muted-foreground px-1.5 py-0.5 bg-muted rounded-full">
              {otherArtifacts.length}
            </span>
          </div>

          {chatId && <SkillDetectionCard artifacts={artifacts} chatId={chatId} />}

          <div className="grid gap-2 sm:grid-cols-2">
            {otherArtifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} onPreview={handlePreview} />
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export default ArtifactsDisplay;
