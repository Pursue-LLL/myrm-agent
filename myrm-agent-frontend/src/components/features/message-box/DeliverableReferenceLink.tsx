'use client';

import React, { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { DeliverableReference } from '@/lib/deliverable-link/parseDeliverableReference';
import {
  openArtifactDeliverable,
  openWorkspaceDeliverable,
} from '@/services/deliverable/openWorkspaceDeliverable';
import type { Artifact } from '@/store/chat/types';

interface DeliverableReferenceLinkProps {
  reference: DeliverableReference;
  label: string;
  chatId?: string;
  workspaceDir?: string;
  messageArtifacts?: Artifact[];
  className?: string;
}

function findArtifactById(artifacts: Artifact[] | undefined, id: string): Artifact | undefined {
  if (!artifacts?.length) {
    return undefined;
  }
  return artifacts.find((a) => a.id === id || a.filename === id);
}

function findArtifactByShortFileId(
  artifacts: Artifact[] | undefined,
  shortFileId: string,
): Artifact | undefined {
  if (!artifacts?.length) {
    return undefined;
  }
  return artifacts.find((a) => a.short_file_id === shortFileId);
}

export default function DeliverableReferenceLink({
  reference,
  label,
  chatId,
  workspaceDir,
  messageArtifacts,
  className,
}: DeliverableReferenceLinkProps) {
  const t = useTranslations('chat.deliverable');
  const [opening, setOpening] = useState(false);

  const fileIdResolvable =
    reference.kind !== 'file_id' ||
    Boolean(findArtifactByShortFileId(messageArtifacts, reference.id));

  const handleClick = useCallback(async () => {
    if (opening || !fileIdResolvable) {
      return;
    }
    setOpening(true);
    try {
      if (reference.kind === 'workspace') {
        await openWorkspaceDeliverable({
          path: reference.path,
          chatId,
          workspaceDir,
        });
        return;
      }

      if (reference.kind === 'file_id') {
        const byShortId = findArtifactByShortFileId(messageArtifacts, reference.id);
        if (byShortId) {
          await openArtifactDeliverable(byShortId);
        }
        return;
      }

      const artifact = findArtifactById(messageArtifacts, reference.id);
      if (artifact) {
        await openArtifactDeliverable(artifact);
        return;
      }

      await openWorkspaceDeliverable({
        path: reference.id,
        chatId,
        workspaceDir,
      });
    } finally {
      setOpening(false);
    }
  }, [chatId, fileIdResolvable, messageArtifacts, opening, reference, workspaceDir]);

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={opening || !fileIdResolvable}
      data-testid="deliverable-reference-link"
      data-deliverable-kind={reference.kind}
      className={cn(
        'inline font-mono text-sm text-[#ED6037] dark:text-orange-400',
        'bg-[#f6f6f1] dark:bg-gray-800 px-1 py-0.5 rounded',
        'underline decoration-dotted decoration-[#ED6037]/40 hover:decoration-[#ED6037]',
        'cursor-pointer transition-colors disabled:opacity-60 disabled:cursor-not-allowed',
        className,
      )}
      title={fileIdResolvable ? label : t('awaitingArtifact')}
    >
      {label}
    </button>
  );
}
