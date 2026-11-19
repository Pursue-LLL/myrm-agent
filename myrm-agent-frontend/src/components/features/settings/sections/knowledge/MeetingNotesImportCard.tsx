'use client';

/**
 * [INPUT]
 * - @/lib/api::apiRequest, ApiError (POS: unified frontend API request entry and its normalized error type)
 * - @/services/wikiService::buildWikiApiPath (POS: Wiki endpoint path builder with optional agent_id query)
 * - POST /wiki/meeting-notes/transcribe with the audio file as multipart form data (chunk size, parallelism and
 *   auto-compile keep the server defaults); transcribing long audio takes minutes, so the request has no client timeout
 * - useTranslations('settings.wiki') (POS: i18n locale namespace)
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
import { ApiError, apiRequest } from '@/lib/api';
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
  risks: string[];
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
      // timeout 0: chunked transcription of up to 500 MB of audio outlasts the 30 s default. silent: the error is
      // shown inline under the form, not as a global toast.
      const payload = await apiRequest<MeetingNotesResponse>(buildWikiApiPath('/wiki/meeting-notes/transcribe'), {
        method: 'POST',
        body: form,
        timeout: 0,
        silent: true,
      });
      setResult(payload);
    } catch (err) {
      // Only server-reported reasons are shown verbatim; transport failures get the localized message.
      setError(err instanceof ApiError && err.message ? err.message : t('meetingNotes.error'));
    } finally {
      setUploading(false);
    }
  }, [t]);

  const formatDuration = (seconds: number): string =>
    t('meetingNotes.durationMinutes', { minutes: Math.round(seconds / 60) });
  const tbd = t('meetingNotes.tbd');

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
            accept={`audio/*,${ACCEPT}`}
            className="block w-full cursor-pointer rounded-lg border border-border bg-background text-sm file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-xs file:font-medium"
            data-testid="meeting-notes-file-input"
          />
          <Button onClick={handleUpload} disabled={uploading} data-testid="meeting-notes-upload-btn">
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileAudio className="w-4 h-4" />}
            {uploading ? t('meetingNotes.processing') : t('meetingNotes.uploadButton')}
          </Button>
        </div>

        {error && (
          <p className="text-sm text-destructive-text" data-testid="meeting-notes-error">
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
            {result.risks.length > 0 && (
              <div>
                <p className="text-xs font-medium">{t('meetingNotes.risks')}</p>
                <ul className="list-disc pl-5 text-xs text-muted-foreground">
                  {result.risks.map((risk) => (
                    <li key={risk}>{risk}</li>
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
                      {item.description} ({item.owner ?? tbd} · {item.due_hint ?? tbd})
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
