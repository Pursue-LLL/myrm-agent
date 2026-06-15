'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import BrandLogo from '@/components/features/app-shell/BrandLogo';
import { cn } from '@/lib/utils/classnameUtils';
import { discoverMigrationSources, type DiscoveryResponse } from '@/services/migrationDiscovery';
import { probeLocalCapabilities, type ProbeLocalResponse } from '@/services/localCapabilitiesProbe';
import { completeOnboarding } from '@/services/onboarding';
import { isLocalMode } from '@/lib/deploy-mode';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import { getActiveSearchServiceConfig } from '@/store/config/searchService';

import MigrationWizardSection from '@/components/features/settings/sections/knowledge/MigrationWizardSection';
import LocalCapabilitiesSetup from './LocalCapabilitiesSetup';
import { Button } from '@/components/primitives/button';

interface OnboardingWizardProps {
  onComplete: () => void;
}

type Step = 'welcome' | 'migration' | 'capabilities' | 'finishing';

const WELCOME_DURATION_MS = 2500;

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const t = useTranslations('boot');
  const [step, setStep] = useState<Step>('welcome');
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null);
  const [probe, setProbe] = useState<ProbeLocalResponse | null>(null);
  const [fadeOut, setFadeOut] = useState(false);
  const [initDone, setInitDone] = useState(false);

  const providers = useProviderStore((s) => s.providers);
  const isInitialized = useProviderStore((s) => s.isInitialized);
  const searchServiceConfigs = useConfigStore((s) => s.searchServiceConfigs);

  const hasEnabledProvider = providers.some(
    (p) => p.isEnabled && (p.apiKeys?.some((k) => k.isActive && k.key) || ['ollama', 'lm_studio'].includes(p.id)),
  );
  const searchConfigured = !!getActiveSearchServiceConfig(searchServiceConfigs);

  // We only run the async probes once on mount
  useEffect(() => {
    let mounted = true;
    const startTime = Date.now();

    const runProbes = async () => {
      try {
        const [discRes, probeRes] = await Promise.all([
          isLocalMode() ? discoverMigrationSources(false).catch(() => null) : Promise.resolve(null),
          isLocalMode() ? probeLocalCapabilities(false).catch(() => null) : Promise.resolve(null),
        ]);

        if (!mounted) return;

        setDiscovery(discRes);
        setProbe(probeRes);

        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, WELCOME_DURATION_MS - elapsed);

        setTimeout(() => {
          if (mounted) setInitDone(true);
        }, remaining);
      } catch {
        if (mounted) setInitDone(true);
      }
    };

    void runProbes();

    return () => {
      mounted = false;
    };
  }, []);

  // When both the minimum welcome duration has passed AND the stores are initialized, we decide the next step
  useEffect(() => {
    if (initDone && isInitialized && step === 'welcome') {
      if (discovery && discovery.sources.length > 0) {
        setStep('migration');
      } else if (isLocalMode() && (!hasEnabledProvider || !searchConfigured)) {
        setStep('capabilities');
      } else {
        handleFinish();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initDone, isInitialized, step, discovery, hasEnabledProvider, searchConfigured]);

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
    if (isLocalMode() && (!hasEnabledProvider || !searchConfigured)) {
      setStep('capabilities');
    } else {
      handleFinish();
    }
  }, [hasEnabledProvider, searchConfigured, handleFinish]);

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
          <div className="text-2xl font-semibold brand-gradient-text">
            {t('title')}
          </div>
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
            <div className="text-center space-y-2 mb-8">
              <h1 className="text-2xl font-bold">{t('onboarding.migrationTitle')}</h1>
              <p className="text-muted-foreground">{t('onboarding.migrationDescription')}</p>
            </div>
            <div className="bg-card border rounded-xl p-6">
              <MigrationWizardSection onMigrationComplete={handleMigrationCompleteOrSkip} />
            </div>
            <div className="flex justify-center mt-6">
              <Button variant="ghost" onClick={handleMigrationCompleteOrSkip}>
                {t('onboarding.skipStep')}
              </Button>
            </div>
          </div>
        )}

        {step === 'capabilities' && (
          <div className="space-y-6">
            <div className="text-center space-y-2 mb-8">
              <h1 className="text-2xl font-bold">{t('onboarding.capabilitiesTitle')}</h1>
              <p className="text-muted-foreground">{t('onboarding.capabilitiesDescription')}</p>
            </div>
            <div className="bg-card border rounded-xl p-6">
              <LocalCapabilitiesSetup probeResult={probe} onComplete={handleFinish} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
