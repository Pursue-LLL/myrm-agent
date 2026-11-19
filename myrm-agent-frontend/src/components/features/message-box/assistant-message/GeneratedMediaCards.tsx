'use client';

/**
 * [INPUT]
 * @/lib/chat/mediaGenerated::{MediaGeneratedEntry,MediaStoredEntry,isMediaTaskEntry} (POS: What a media tool call registered)
 * @/components/features/task-card::{ImageTaskCard,VideoTaskCard} (POS: Async media task cards)
 * @/components/features/image-gen/{ImageResultCard,useEditGeneratedImage} (POS: Image result renderer and its edit action)
 * ../TtsAudioCard (POS: Inline speech player)
 *
 * [OUTPUT]
 * GeneratedMediaCards: One card per registered media generation, in the order the tools produced them.
 *
 * [POS]
 * Renders the media a turn generated. An entry either names an async task (the card follows its progress) or
 * a stored media reference (the card shows it right away). The cards are driven by what the tools registered,
 * not by anything the model wrote, so they appear whatever the reply says.
 */

import { ImageResultCard } from '@/components/features/image-gen/ImageResultCard';
import { useEditGeneratedImage } from '@/components/features/image-gen/useEditGeneratedImage';
import { ImageTaskCard, VideoTaskCard } from '@/components/features/task-card';
import { isMediaTaskEntry, type MediaGeneratedEntry, type MediaStoredEntry } from '@/lib/chat/mediaGenerated';
import TtsAudioCard from '../TtsAudioCard';

function StoredImageCard({ entry }: { entry: MediaStoredEntry }) {
  const editImage = useEditGeneratedImage();
  return <ImageResultCard images={[{ url: entry.media }]} model={entry.model} onEditRequest={editImage} />;
}

export function GeneratedMediaCards({ entries }: { entries: MediaGeneratedEntry[] }) {
  return (
    <>
      {entries.map((entry) => {
        if (isMediaTaskEntry(entry)) {
          const TaskCard = entry.kind === 'video' ? VideoTaskCard : ImageTaskCard;
          return <TaskCard key={`${entry.kind}:${entry.task_id}`} task_id={entry.task_id} />;
        }
        if (entry.kind === 'tts') {
          return (
            <TtsAudioCard
              key={`tts:${entry.media}`}
              url={entry.media}
              model={entry.model}
              durationSeconds={entry.duration_seconds}
            />
          );
        }
        return <StoredImageCard key={`image:${entry.media}`} entry={entry} />;
      })}
    </>
  );
}
