/**
 * [INPUT]
 * - @/services/memory/profileNotes: getProfileNotesContents, updateProfileNotesContents, checkProfileNotesIntake
 * - @/services/memory/profileNotes: LayerWatermarkResponse, WatermarkLevel, ProfileNotesIntakeResponse
 * - ./WatermarkBar: WatermarkBar, levelForRatio
 * - @/components/primitives: Card, Button, Textarea, Input
 * - next-intl::useTranslations (POS: Internationalization hook)
 *
 * [OUTPUT]
 * - DualLayerMemoryCard: React component rendering User Profile & Agent Notes dual HUD with watermark gauges and intake filter probe.
 *
 * [POS]
 * Reusable agent memory dashboard component enforcing the capacity limits (USER <= 1375c, MEMORY <= 2200c)
 * and noise purging verification. Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, CheckCircle2, Filter, Loader2, RefreshCw, Save, ShieldCheck, User, Wrench } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { cn } from '@/lib/utils/classnameUtils';
import {
  checkProfileNotesIntake,
  getProfileNotesContents,
  type LayerWatermarkResponse,
  type ProfileNotesIntakeResponse,
  updateProfileNotesContents,
} from '@/services/memory/profileNotes';

import { levelForRatio, WatermarkBar } from './WatermarkBar';

interface DualLayerMemoryCardProps {
  className?: string;
  onSaved?: () => void;
}

const DEFAULT_USER_MAX = 1375;
const DEFAULT_MEMORY_MAX = 2200;

type FeedbackKey = 'loadFailed' | 'saved' | 'saveFailed';

/** Watermark of a layer after the user edits its text, measured against the layer's default capacity. */
function watermarkAfterEdit(prev: LayerWatermarkResponse, text: string, maxChars: number): LayerWatermarkResponse {
  const ratio = text.length / maxChars;
  return { ...prev, current_chars: text.length, usage_ratio: ratio, level: levelForRatio(ratio) };
}

export function DualLayerMemoryCard({ className, onSaved }: DualLayerMemoryCardProps) {
  const t = useTranslations('memory.dualLayer');
  const [userContent, setUserContent] = useState('');
  const [memoryContent, setMemoryContent] = useState('');
  const [userWatermark, setUserWatermark] = useState<LayerWatermarkResponse>({
    layer: 'user',
    current_chars: 0,
    max_chars: DEFAULT_USER_MAX,
    usage_ratio: 0,
    level: 'safe',
    warning_message: null,
  });
  const [memoryWatermark, setMemoryWatermark] = useState<LayerWatermarkResponse>({
    layer: 'memory',
    current_chars: 0,
    max_chars: DEFAULT_MEMORY_MAX,
    usage_ratio: 0,
    level: 'safe',
    warning_message: null,
  });

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [feedbackKey, setFeedbackKey] = useState<FeedbackKey | null>(null);

  // Intake test probe states
  const [testProbeText, setTestProbeText] = useState('');
  const [isProbing, setIsProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<ProfileNotesIntakeResponse | null>(null);

  const fetchContents = useCallback(async () => {
    setIsLoading(true);
    setFeedbackKey(null);
    try {
      const data = await getProfileNotesContents();
      setUserContent(data.user_content);
      setMemoryContent(data.memory_content);
      setUserWatermark(data.user_watermark);
      setMemoryWatermark(data.memory_watermark);
    } catch {
      setFeedbackKey('loadFailed');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchContents();
  }, [fetchContents]);

  const handleSave = async () => {
    setIsSaving(true);
    setFeedbackKey(null);
    try {
      const updated = await updateProfileNotesContents({
        user_content: userContent,
        memory_content: memoryContent,
      });
      setUserContent(updated.user_content);
      setMemoryContent(updated.memory_content);
      setUserWatermark(updated.user_watermark);
      setMemoryWatermark(updated.memory_watermark);
      setFeedbackKey('saved');
      onSaved?.();
    } catch {
      setFeedbackKey('saveFailed');
    } finally {
      setIsSaving(false);
    }
  };

  const handleProbeIntake = async () => {
    if (!testProbeText.trim()) {
      return;
    }
    setIsProbing(true);
    try {
      const res = await checkProfileNotesIntake({ content: testProbeText.trim() });
      setProbeResult(res);
    } catch {
      setProbeResult({
        accepted: false,
        target_layer: null,
        rejected_reason: t('intakeCheckFailed'),
        garbage_category: 'ERROR',
      });
    } finally {
      setIsProbing(false);
    }
  };

  return (
    <Card className={cn('w-full border border-border shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-base font-semibold">{t('title')}</CardTitle>
              <CardDescription className="text-xs">
                {t('description', { userMax: DEFAULT_USER_MAX, memoryMax: DEFAULT_MEMORY_MAX })}
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void fetchContents()}
              disabled={isLoading || isSaving}
              className="h-8 gap-1 px-2 text-xs"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
              {t('refresh')}
            </Button>
            <Button
              size="sm"
              onClick={() => void handleSave()}
              disabled={isLoading || isSaving}
              className="h-8 gap-1 px-3 text-xs"
            >
              {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              {t('save')}
            </Button>
          </div>
        </div>
        {feedbackKey && (
          <div className="mt-2 rounded-md bg-secondary/50 px-2.5 py-1.5 text-xs text-muted-foreground">
            {t(`feedback.${feedbackKey}`)}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* Dual columns */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {/* Left column: User profile */}
          <div className="space-y-2 rounded-lg border border-border/80 bg-background/50 p-3">
            <div className="flex items-center gap-1.5">
              <User className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold">{t('userProfile.title')}</span>
              <span className="text-[11px] text-muted-foreground">{t('budget', { max: DEFAULT_USER_MAX })}</span>
            </div>
            <p className="text-[11px] text-muted-foreground">{t('userProfile.hint')}</p>
            <WatermarkBar watermark={userWatermark} />
            <Textarea
              className="min-h-[140px] resize-y font-mono text-xs leading-relaxed"
              placeholder={t('userProfile.placeholder')}
              value={userContent}
              onChange={(e) => {
                const text = e.target.value;
                setUserContent(text);
                setUserWatermark((prev) => watermarkAfterEdit(prev, text, DEFAULT_USER_MAX));
              }}
              disabled={isLoading}
            />
          </div>

          {/* Right column: Agent working notes */}
          <div className="space-y-2 rounded-lg border border-border/80 bg-background/50 p-3">
            <div className="flex items-center gap-1.5">
              <Wrench className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold">{t('agentNotes.title')}</span>
              <span className="text-[11px] text-muted-foreground">{t('budget', { max: DEFAULT_MEMORY_MAX })}</span>
            </div>
            <p className="text-[11px] text-muted-foreground">{t('agentNotes.hint')}</p>
            <WatermarkBar watermark={memoryWatermark} />
            <Textarea
              className="min-h-[140px] resize-y font-mono text-xs leading-relaxed"
              placeholder={t('agentNotes.placeholder')}
              value={memoryContent}
              onChange={(e) => {
                const text = e.target.value;
                setMemoryContent(text);
                setMemoryWatermark((prev) => watermarkAfterEdit(prev, text, DEFAULT_MEMORY_MAX));
              }}
              disabled={isLoading}
            />
          </div>
        </div>

        {/* Bottom: Intake Filter Probe */}
        <div className="rounded-lg border border-dashed border-border bg-muted/20 p-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
            <Filter className="h-3.5 w-3.5 text-primary" />
            <span>{t('intakeProbe.title')}</span>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              className="h-8 text-xs font-mono"
              placeholder={t('intakeProbe.placeholder')}
              value={testProbeText}
              onChange={(e) => setTestProbeText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void handleProbeIntake();
                }
              }}
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void handleProbeIntake()}
              disabled={isProbing || !testProbeText.trim()}
              className="h-8 shrink-0 text-xs gap-1"
            >
              {isProbing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              {t('intakeProbe.check')}
            </Button>
          </div>

          {probeResult && (
            <div
              className={cn(
                'mt-2 flex items-start gap-2 rounded-md p-2 text-xs',
                probeResult.accepted
                  ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                  : 'bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
              )}
            >
              {probeResult.accepted ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
              )}
              <div className="space-y-0.5">
                <div className="font-medium">
                  {probeResult.accepted
                    ? t('intakeProbe.accepted', {
                        layer: probeResult.target_layer?.toUpperCase() ?? t('intakeProbe.longTerm'),
                      })
                    : t('intakeProbe.rejected', { category: probeResult.garbage_category ?? 'TRANSIENT' })}
                </div>
                {probeResult.rejected_reason && <p className="text-[11px] opacity-90">{probeResult.rejected_reason}</p>}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
export default DualLayerMemoryCard;
