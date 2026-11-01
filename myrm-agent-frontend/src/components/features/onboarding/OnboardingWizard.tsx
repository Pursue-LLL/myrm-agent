'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import BrandLogo from '@/components/features/app-shell/BrandLogo';
import { cn } from '@/lib/utils/classnameUtils';
import { completeOnboarding } from '@/services/onboarding';
import useProviderStore from '@/store/useProviderStore';

import { RestoreEntry } from '@/components/features/instance-archive/RestoreEntry';
import MigrationWizardSection from '@/components/features/settings/sections/knowledge/MigrationWizardSection';
import FirstRunDoctorCard from './FirstRunDoctorCard';
import SmartRoutingStep from './SmartRoutingStep';
import SmartGuardStep from './SmartGuardStep';
import ToolsConnectOnboardingStep from './ToolsConnectOnboardingStep';
import ThemeOnboardingStep from './ThemeOnboardingStep';
import { Button } from '@/components/primitives/button';
import { getConfigSyncManager } from '@/services/config';
import type { SecurityConfigValue } from '@/services/config/types';

interface OnboardingWizardProps {
  onComplete: () => void;
}

type Step =
  'welcome' | 'migration' | 'tools_connect' | 'health' | 'routing' | 'smart_guard' | 'theme_pick' | 'finishing';

const WELCOME_DURATION_MS = 2500;

/** First-run wizard of a hosted sandbox. Local installs skip it: they land on the home page, where `NoProviderBanner` asks for a provider. */
export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const t = useTranslations('boot');
  const [step, setStep] = useState<Step>('welcome');
  const [welcomeElapsed, setWelcomeElapsed] = useState(false);
  const [fadeOut, setFadeOut] = useState(false);

  const isInitialized = useProviderStore((s) => s.isInitialized);
  const defaultModelConfig = useProviderStore((s) => s.defaultModelConfig);
  const getEnabledModels = useProviderStore((s) => s.getEnabledModels);

  const routingAlreadyEnabled = defaultModelConfig.routingConfig?.enabled ?? false;

  const shouldShowRouting = useCallback(() => {
    if (routingAlreadyEnabled) {
      return false;
    }
    return getEnabledModels().length >= 2;
  }, [routingAlreadyEnabled, getEnabledModels]);

  const shouldShowSmartGuard = useCallback(() => {
    if (getEnabledModels().length === 0) {
      return false;
    }
    const secConfig = getConfigSyncManager().get('securityConfig') as SecurityConfigValue | null;
    return !secConfig?.autoReviewEnabled;
  }, [getEnabledModels]);

  useEffect(() => {
    const timer = setTimeout(() => setWelcomeElapsed(true), WELCOME_DURATION_MS);
    return () => clearTimeout(timer);
  }, []);

  // The welcome screen stays until its minimum duration has passed AND the provider store is initialized.
  useEffect(() => {
    if (welcomeElapsed && isInitialized && step === 'welcome') {
      setStep('migration');
    }
  }, [welcomeElapsed, isInitialized, step]);

  const advanceToThemePick = useCallback(() => {
    setStep('theme_pick');
  }, []);

  const moveToSmartGuardOrNext = useCallback(() => {
    if (shouldShowSmartGuard()) {
      setStep('smart_guard');
      return;
    }
    advanceToThemePick();
  }, [advanceToThemePick, shouldShowSmartGuard]);

  const handleFinish = useCallback(async () => {
    setStep('finishing');
    setFadeOut(true);
    try {
      await completeOnboarding();
    } catch {
      // Ignore errors
    }
    setTimeout(onComplete, 400);
  }, [onComplete]);

  const handleMigrationCompleteOrSkip = useCallback(() => {
    setStep('tools_connect');
  }, []);

  const handleToolsConnectCompleteOrSkip = useCallback(() => {
    setStep('health');
  }, []);

  const handleHealthCompleteOrSkip = useCallback(() => {
    if (shouldShowRouting()) {
      setStep('routing');
    } else {
      moveToSmartGuardOrNext();
    }
  }, [moveToSmartGuardOrNext, shouldShowRouting]);

  if (step === 'welcome' || step === 'finishing') {
    return (
      <div
        className={cn(
          'fixed inset-0 z-50 flex flex-col items-center justify-center',
          'bg-background select-none',
          'transition-opacity duration-400 ease-out',
          fadeOut ? 'opacity-0' : 'opacity-100',
        )}
      >
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
          <div className="absolute -top-24 left-1/4 h-72 w-72 rounded-full bg-primary/10 blur-3xl animate-pulse" />
          <div className="absolute bottom-0 right-1/4 h-64 w-64 rounded-full bg-accent-warm/10 blur-3xl animate-pulse" />
        </div>

        <div className="relative flex flex-col items-center gap-4 animate-in fade-in zoom-in duration-700">
          <BrandLogo size={64} priority className="w-16 h-16" />
          <div className="text-2xl font-semibold brand-gradient-text">{t('title')}</div>
          <div className="flex items-center gap-2 mt-4 text-sm text-muted-foreground">
            <span className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
            {t('step.initServices')}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background overflow-y-auto">
      <div className="flex-1 w-full max-w-4xl mx-auto p-6 sm:p-10 flex flex-col justify-center min-h-full animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="mb-8 flex items-center justify-center">
          <BrandLogo size={40} className="w-10 h-10" />
        </div>

        {step === 'migration' && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-primary/30 bg-primary/5 p-6 mb-4 flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="space-y-1 text-center sm:text-left">
                <div className="font-semibold text-foreground flex items-center justify-center sm:justify-start gap-2">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  {t('onboarding.instantStartTitle')}
                </div>
                <p className="text-xs text-muted-foreground">{t('onboarding.instantStartDescription')}</p>
              </div>
              <Button onClick={handleFinish} className="gap-2 shrink-0">
                {t('onboarding.instantStartButton')}
              </Button>
            </div>
            <div className="text-center space-y-2 mb-8">
              <h1 className="text-2xl font-bold">{t('onboarding.migrationCloudTitle')}</h1>
              <p className="text-muted-foreground">{t('onboarding.migrationCloudDescription')}</p>
            </div>
            <div className="bg-card border rounded-xl p-6">
              <MigrationWizardSection onMigrationComplete={handleMigrationCompleteOrSkip} />
            </div>
            <RestoreEntry />
            <div className="flex justify-center mt-6">
              <Button variant="ghost" onClick={handleMigrationCompleteOrSkip}>
                {t('onboarding.skipStep')}
              </Button>
            </div>
          </div>
        )}

        {step === 'tools_connect' && (
          <div className="space-y-6">
            <div className="text-center space-y-2 mb-8">
              <h1 className="text-2xl font-bold">{t('onboarding.toolsConnect.pageTitle')}</h1>
              <p className="text-muted-foreground">{t('onboarding.toolsConnect.pageDescription')}</p>
            </div>
            <div className="bg-card border rounded-xl p-6">
              <ToolsConnectOnboardingStep
                onComplete={handleToolsConnectCompleteOrSkip}
                onSkip={handleToolsConnectCompleteOrSkip}
              />
            </div>
          </div>
        )}

        {step === 'health' && (
          <div className="space-y-6">
            <div className="text-center space-y-2 mb-8">
              <h1 className="text-2xl font-bold">{t('onboarding.doctorTitle')}</h1>
              <p className="text-muted-foreground">{t('onboarding.doctorDescription')}</p>
            </div>
            <div className="bg-card border rounded-xl p-6">
              <FirstRunDoctorCard />
            </div>
            <div className="flex justify-center gap-3 mt-6">
              <Button variant="ghost" onClick={handleHealthCompleteOrSkip}>
                {t('onboarding.skipStep')}
              </Button>
              <Button onClick={handleHealthCompleteOrSkip}>{t('onboarding.doctorContinueButton')}</Button>
            </div>
          </div>
        )}

        {step === 'routing' && (
          <div className="space-y-6">
            <div className="text-center space-y-2 mb-8">
              <h1 className="text-2xl font-bold">{t('onboarding.routing.pageTitle')}</h1>
              <p className="text-muted-foreground">{t('onboarding.routing.pageDescription')}</p>
            </div>
            <div className="bg-card border rounded-xl p-6">
              <SmartRoutingStep onComplete={moveToSmartGuardOrNext} onSkip={moveToSmartGuardOrNext} />
            </div>
          </div>
        )}

        {step === 'smart_guard' && (
          <div className="space-y-6">
            <div className="text-center space-y-2 mb-8">
              <h1 className="text-2xl font-bold">{t('onboarding.smartGuard.pageTitle')}</h1>
              <p className="text-muted-foreground">{t('onboarding.smartGuard.pageDescription')}</p>
            </div>
            <div className="bg-card border rounded-xl p-6">
              <SmartGuardStep onComplete={advanceToThemePick} onSkip={advanceToThemePick} />
            </div>
          </div>
        )}

        {step === 'theme_pick' && (
          <div className="space-y-6">
            <div className="text-center space-y-2 mb-8">
              <h1 className="text-2xl font-bold">{t('onboarding.themePick.pageTitle')}</h1>
              <p className="text-muted-foreground">{t('onboarding.themePick.pageDescription')}</p>
            </div>
            <div className="bg-card border rounded-xl p-6">
              <ThemeOnboardingStep onComplete={() => void handleFinish()} onSkip={() => void handleFinish()} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
