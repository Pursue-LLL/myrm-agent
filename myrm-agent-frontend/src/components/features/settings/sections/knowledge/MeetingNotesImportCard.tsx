'use client';

/**
 * [INPUT]
 * fetch POST {audio file, chunk_seconds, max_parallel, auto_compile} -> /api/v1/wiki/meeting-notes/transcribe
 *
 * [OUTPUT]
 * MeetingNotesImportCard: meeting audio import card in knowledge settings.
 *
 * [POS]
 * Meeting audio import card. Upload audio, run chunked parallel ASR + LLM minutes
 * distillation + wiki raw publish, then surface structured minutes to the user.
 */

import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FileAudio, Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { buildWikiApiPath } from '@/services/wikiService';

interface MeetingNotesResponse {
  success: boolean;
  chunk_count: number;
  duration_seconds: number;
  language?: string | null;
  title: string;
  summary: string;
  decisions: string[];
  debate_points: string[];
  action_items: Array<{ description: string; owner: string | null; due_hint: string | null }>;
  published_wiki_paths: string[];
  error: string;
}

const ACCEPT = '.mp3,.m4a,.wav,.webm,.ogg,.flac,.opus';

export default function MeetingNotesImportCard() {
  const t = useTranslations('settings.wiki');
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MeetingNotesResponse | null>(null);

  const handleUpload = useCallback(async () => {
    const file = inputRef.current?.files?.[0];
    if (!file) {
      return;
    }
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await fetch(buildWikiApiPath('/wiki/meeting-notes/transcribe'), {
        method: 'POST',
        body: form,
      });
      const payload = (await response.json()) as MeetingNotesResponse;
      if (!response.ok || !payload.success) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }, []);

  const formatDuration = (seconds: number): string => {
    const mins = Math.round(seconds / 60);
    return `${mins} min`;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileAudio className="w-5 h-5" />
          {t('meetingNotes.title')}
        </CardTitle>
        <CardDescription>{t('meetingNotes.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            ref={inputRef}
            type="file"
            accept="audio/*,.mp3,.m4a,.wav,.webm,.ogg,.flac,.opus"
            className="block w-full cursor-pointer rounded-lg border border-border bg-background text-sm file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-xs file:font-medium"
            data-testid="meeting-notes-file-input"
          />
          <Button onClick={handleUpload} disabled={uploading} data-testid="meeting-notes-upload-btn">
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileAudio className="w-4 h-4" />}
            {uploading ? t('meetingNotes.processing') : t('meetingNotes.uploadButton')}
          </Button>
        </div>

        {error && (
          <p className="text-sm text-destructive" data-testid="meeting-notes-error">
            {error}
          </p>
        )}

        {result && (
          <div className="space-y-3 rounded-lg border border-border/60 p-4" data-testid="meeting-notes-result">
            <div className="text-sm font-medium">
              {result.title}
              <span className="ml-2 text-xs text-muted-foreground">
                {result.chunk_count} · {formatDuration(result.duration_seconds)}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">{result.summary}</p>
            {result.decisions.length > 0 && (
              <div>
                <p className="text-xs font-medium">{t('meetingNotes.decisions')}</p>
                <ul className="list-disc pl-5 text-xs text-muted-foreground">
                  {result.decisions.map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
              </div>
            )}
            {result.debate_points.length > 0 && (
              <div>
                <p className="text-xs font-medium">{t('meetingNotes.debates')}</p>
                <ul className="list-disc pl-5 text-xs text-muted-foreground">
                  {result.debate_points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
            {result.action_items.length > 0 && (
              <div>
                <p className="text-xs font-medium">{t('meetingNotes.actionItems')}</p>
                <ul className="list-disc pl-5 text-xs text-muted-foreground">
                  {result.action_items.map((item) => (
                    <li key={item.description}>
                      {item.description} ({item.owner ?? 'TBD'} · {item.due_hint ?? 'TBD'})
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result.published_wiki_paths.length > 0 && (
              <p className="text-xs text-muted-foreground">{result.published_wiki_paths.join(', ')}</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}