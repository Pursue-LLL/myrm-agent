'use client';

import React, { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconShieldCheck } from '@/components/features/icons/PremiumIcons';
import { Switch } from '@/components/primitives/switch';
import EnabledModelSelect, { type EnabledModel } from '../../default-model/EnabledModelSelect';
import type { SingleModelSelection, ProviderConfig } from '@/store/config/providerTypes';
import SettingsSection from '../SettingsSection';

interface SmartIntentGuardEditorProps {
  autoReviewEnabled: boolean;
  autoReviewModel: SingleModelSelection | null;
  enabledModels: EnabledModel[];
  providers: ProviderConfig[];
  onToggle: (checked: boolean) => void;
  onModelChange: (model: SingleModelSelection | null) => void;
}

export const SmartIntentGuardEditor = memo<SmartIntentGuardEditorProps>(
  ({ autoReviewEnabled, autoReviewModel, enabledModels, providers, onToggle, onModelChange }) => {
    const t = useTranslations('settings.securityPolicy');

    return (
      <SettingsSection
        title={t('autoReview.title', { default: 'Smart Intent Guard' })}
        description={t('autoReview.description', {
          default:
            'Use an LLM to automatically review high-risk tool calls (like shell commands or network requests) against your original intent. If the action matches your intent, it is silently approved, reducing interruption fatigue.',
        })}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4 p-4 rounded-lg border border-border bg-background">
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <IconShieldCheck className="h-4 w-4 text-green-500" />
                <span className="font-medium">
                  {t('autoReview.enableLabel', { default: 'Enable Smart Intent Guard' })}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {t('autoReview.enableDesc', {
                  default:
                    'When enabled, an LLM will evaluate potentially dangerous tool calls before interrupting you.',
                })}
              </p>
            </div>
            <Switch checked={autoReviewEnabled} onCheckedChange={onToggle} />
          </div>

          <div className="p-4 rounded-lg border border-border bg-muted/30 space-y-3">
            <EnabledModelSelect
              label={t('autoReview.selectModel', { default: 'Select Reviewer Model' })}
              value={autoReviewModel}
              onChange={onModelChange}
              enabledModels={enabledModels}
              providers={providers}
              placeholder={t('autoReview.selectModelPlaceholder', {
                default: 'Select a fast model (e.g. GPT-4o-mini)',
              })}
            />
            {autoReviewEnabled && !autoReviewModel && enabledModels.length > 0 && (
              <div className="flex items-start gap-2 p-2.5 rounded-md bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800/50">
                <IconShieldCheck className="h-3.5 w-3.5 text-blue-500 mt-0.5 shrink-0" />
                <p className="text-xs text-blue-700 dark:text-blue-400">
                  {t('autoReview.noModelHint', {
                    default:
                      'Smart Intent Guard is active using your default model. For optimal latency and cost, consider selecting a dedicated fast model (e.g. GPT-4o-mini).',
                  })}
                </p>
              </div>
            )}
            {autoReviewEnabled && autoReviewModel && (
              <p className="text-xs text-muted-foreground mt-2">
                {t('autoReview.modelRecommendation', {
                  default:
                    'Recommendation: Use a fast, low-cost model like GPT-4o-mini or Claude 3 Haiku for optimal latency.',
                })}
              </p>
            )}
            {autoReviewEnabled && autoReviewModel && (
              <p className="text-xs text-muted-foreground mt-1">
                {t('autoReview.shellEscalationHint', {
                  default:
                    'Note: In Smart Intent Guard mode, high-risk operations (e.g. shell commands) will be reviewed by the security model even if your permission rules set them to "Allow". Trivially safe commands (ls, cat, git status, etc.) are fast-tracked without LLM review.',
                })}
              </p>
            )}
          </div>
        </div>
      </SettingsSection>
    );
  },
);

SmartIntentGuardEditor.displayName = 'SmartIntentGuardEditor';
