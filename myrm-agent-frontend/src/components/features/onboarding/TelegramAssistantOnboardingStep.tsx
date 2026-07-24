'use client';

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Bot, Eye, EyeOff, Loader2, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { ApiError } from '@/lib/api';
import { isSandbox } from '@/lib/deploy-mode';
import {
  applyTelegramAssistantOnboarding,
  type TelegramAssistantOnboardingResponse,
} from '@/services/onboarding';

interface TelegramAssistantOnboardingStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

interface PendingConnectionState {
  botUsername: string;
}

const ONBOARDING_RETRYABLE_CONFLICT_CODE = 'TELEGRAM_ONBOARDING_IN_PROGRESS';
const ONBOARDING_MAX_ATTEMPTS = 2;

function isOnboardingConflictError(error: unknown): boolean {
  if (!(error instanceof ApiError)) {
    return false;
  }
  if (error.code !== 409) {
    return false;
  }
  const detailCode = error.data?.code;
  if (typeof detailCode === 'string') {
    return detailCode === ONBOARDING_RETRYABLE_CONFLICT_CODE;
  }
  return error.message.toLowerCase().includes('already in progress');
}

function parseErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  return fallback;
}

export default function TelegramAssistantOnboardingStep({
  onComplete,
  onSkip,
}: TelegramAssistantOnboardingStepProps) {
  const t = useTranslations('boot.onboarding.telegramAssistant');
  const sandbox = isSandbox();

  const [botToken, setBotToken] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [assistantName, setAssistantName] = useState('');
  const [assistantDescription, setAssistantDescription] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingConnection, setPendingConnection] = useState<PendingConnectionState | null>(null);

  const canSubmit = useMemo(() => botToken.trim().length > 0 && !loading, [botToken, loading]);

  const handleSubmit = useCallback(async () => {
    const normalizedToken = botToken.trim();
    if (!normalizedToken) {
      setError(t('tokenRequired'));
      return;
    }

    const normalizedWebhook = webhookUrl.trim();
    if (normalizedWebhook && !normalizedWebhook.startsWith('https://')) {
      setError(t('webhookHttpsRequired'));
      return;
    }

    setError(null);
    setPendingConnection(null);
    setLoading(true);
    try {
      const payload = {
        botToken: normalizedToken,
        webhookUrl: normalizedWebhook || undefined,
        assistantName: assistantName.trim() || t('defaultAssistantName'),
        assistantDescription: assistantDescription.trim() || undefined,
      };

      let result: TelegramAssistantOnboardingResponse | null = null;
      for (let attempt = 1; attempt <= ONBOARDING_MAX_ATTEMPTS; attempt += 1) {
        try {
          result = await applyTelegramAssistantOnboarding(payload);
          break;
        } catch (submitError) {
          const canRetry = isOnboardingConflictError(submitError) && attempt < ONBOARDING_MAX_ATTEMPTS;
          if (canRetry) {
            toast.info(t('retryingToast'));
            continue;
          }
          if (isOnboardingConflictError(submitError)) {
            const friendlyMessage = t('inProgressFriendlyError');
            setError(friendlyMessage);
            toast.error(friendlyMessage);
            return;
          }
          throw submitError;
        }
      }
      if (!result) {
        const fallbackMessage = t('inProgressFriendlyError');
        setError(fallbackMessage);
        toast.error(fallbackMessage);
        return;
      }

      if (!result.connected) {
        setPendingConnection({
          botUsername: result.botUsername,
        });
        toast.info(t('pendingToast'));
        return;
      }
      toast.success(
        t('successToast', {
          agentName: result.agentName,
        }),
      );
      onComplete();
    } catch (submitError) {
      const message = parseErrorMessage(submitError, t('setupFailed'));
      setError(message);
      toast.error(t('setupFailedToast'));
    } finally {
      setLoading(false);
    }
  }, [assistantDescription, assistantName, botToken, onComplete, t, webhookUrl]);

  return (
    <div className="space-y-6" data-testid="telegram-onboarding-step">
      <div className="flex items-start gap-4 rounded-xl border bg-card p-5">
        <div className="rounded-xl bg-primary/10 p-3">
          <Bot className="h-6 w-6 text-primary" />
        </div>
        <div className="space-y-2">
          <h3 className="text-lg font-semibold">{t('title')}</h3>
          <p className="text-sm text-muted-foreground">{t('description')}</p>
          <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
            <ShieldCheck className="h-3.5 w-3.5" />
            {t('safetyHint')}
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="onboarding-telegram-token">{t('tokenLabel')}</Label>
          <div className="relative">
            <Input
              id="onboarding-telegram-token"
              type={showToken ? 'text' : 'password'}
              value={botToken}
              onChange={(event) => setBotToken(event.target.value)}
              placeholder={t('tokenPlaceholder')}
              className="pr-10"
              autoComplete="off"
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
              onClick={() => setShowToken((value) => !value)}
              aria-label={showToken ? t('hideToken') : t('showToken')}
            >
              {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {!sandbox && (
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="onboarding-telegram-webhook">{t('webhookLabel')}</Label>
            <Input
              id="onboarding-telegram-webhook"
              type="url"
              value={webhookUrl}
              onChange={(event) => setWebhookUrl(event.target.value)}
              placeholder={t('webhookPlaceholder')}
            />
            <p className="text-xs text-muted-foreground">{t('webhookHint')}</p>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="onboarding-telegram-agent-name">{t('assistantNameLabel')}</Label>
          <Input
            id="onboarding-telegram-agent-name"
            value={assistantName}
            onChange={(event) => setAssistantName(event.target.value)}
            placeholder={t('defaultAssistantName')}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="onboarding-telegram-agent-description">{t('assistantDescriptionLabel')}</Label>
          <Input
            id="onboarding-telegram-agent-description"
            value={assistantDescription}
            onChange={(event) => setAssistantDescription(event.target.value)}
            placeholder={t('assistantDescriptionPlaceholder')}
          />
        </div>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {pendingConnection ? (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
          <p className="font-medium text-amber-800 dark:text-amber-200">{t('pendingTitle')}</p>
          <p className="mt-1 text-amber-700 dark:text-amber-300">
            {t('pendingDescription', {
              botUsername: pendingConnection.botUsername ? `@${pendingConnection.botUsername}` : 'Telegram',
            })}
          </p>
        </div>
      ) : null}

      <div className="flex flex-col items-center gap-3 pt-2">
        <Button size="lg" className="w-full sm:w-auto min-w-[240px]" onClick={handleSubmit} disabled={!canSubmit}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          {pendingConnection ? t('retryButton') : t('setupButton')}
        </Button>
        {pendingConnection ? (
          <Button variant="secondary" size="sm" onClick={onComplete} disabled={loading}>
            {t('continueButton')}
          </Button>
        ) : (
          <Button variant="ghost" size="sm" onClick={onSkip} disabled={loading}>
            {t('skipButton')}
          </Button>
        )}
      </div>
    </div>
  );
}
