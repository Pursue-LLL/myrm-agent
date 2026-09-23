'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/primitives/dialog';
import { CheckCircle2, CircleDashed, Loader2, MessageSquare, Sparkles, TriangleAlert } from 'lucide-react';
import {
  getTemplates,
  instantiateTemplate,
  getAgentReadiness,
  type TemplateListItem,
  type AgentReadinessReport,
} from '@/services/agent';
import { toast } from '@/hooks/shared/useToast';

type Step = 'template' | 'readiness' | 'verify' | 'done';

export function AgentSetupWizard({
  open,
  onOpenChange,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}) {
  const t = useTranslations('Agent.setupWizard');
  const [step, setStep] = useState<Step>('template');
  const [templates, setTemplates] = useState<TemplateListItem[] | null>(null);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [agentName, setAgentName] = useState('');
  const [creating, setCreating] = useState(false);
  const [report, setReport] = useState<AgentReadinessReport | null>(null);
  const [checking, setChecking] = useState(false);

  const DRAFT_KEY = 'myrm-agent-setup-wizard-draft';
  const finishedRef = useRef(false);

  const runReadinessCheck = async (id: string) => {
    setChecking(true);
    try {
      setReport(await getAgentReadiness(id));
    } catch {
      toast.error(t('readiness.error', { fallback: 'Failed to check readiness.' }));
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    if (!open) {
      return;
    }
    try {
      const raw = window.localStorage.getItem(DRAFT_KEY);
      if (!raw) {
        return;
      }
      const draft = JSON.parse(raw) as { step?: Step; agentId?: string; agentName?: string };
      if (draft.agentId) {
        setAgentId(draft.agentId);
        setAgentName(draft.agentName || '');
        if (draft.step === 'verify' || draft.step === 'done') {
          setStep(draft.step);
        } else {
          setStep('readiness');
          void runReadinessCheck(draft.agentId);
        }
      }
    } catch {
      // Corrupt draft must never block setup.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open || finishedRef.current) {
      return;
    }
    try {
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify({ step, agentId, agentName }));
    } catch {
      // Storage failure must never block setup.
    }
  }, [open, step, agentId, agentName]);

  const resetTransient = () => {
    setReport(null);
  };

  const handleOpenChange = (next: boolean) => {
    if (next) {
      finishedRef.current = false;
    } else {
      setStep('template');
      setAgentId(null);
      setAgentName('');
      resetTransient();
    }
    onOpenChange(next);
  };

  useEffect(() => {
    if (!open || templates !== null || loadingTemplates) {
      return;
    }
    setLoadingTemplates(true);
    getTemplates()
      .then(setTemplates)
      .catch(() => {
        toast.error(t('template.error', { fallback: 'Failed to load templates.' }));
      })
      .finally(() => setLoadingTemplates(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open ]);

  const handleInstantiate = async (templateId: string, name: string) => {
    setCreating(true);
    try {
      const agent = await instantiateTemplate(templateId);
      setAgentId(agent.id);
      setAgentName(name || agent.name);
      setStep('readiness');
      await runReadinessCheck(agent.id);
    } catch {
      toast.error(t('template.createError', { fallback: 'Failed to create agent.' }));
    } finally {
      setCreating(false);
    }
  };

  const handleFinish = () => {
    finishedRef.current = true;
    try {
      window.localStorage.removeItem(DRAFT_KEY);
    } catch {
      // Storage failure must never block setup.
    }
    onDone();
    onOpenChange(false);
    setStep('template');
    setAgentId(null);
    setAgentName('');
    resetTransient();
  };

  const handleSkip = () => {
    onOpenChange(false);
  };

  const isBlocked = report?.overall_level === 'blocked';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            {t('title', { fallback: 'Guided setup' })}
          </DialogTitle>
        </DialogHeader>

        {step === 'template' && (
          <div className="grid gap-2 py-2">
            <p className="text-sm text-muted-foreground">
              {t('template.hint', { fallback: 'Pick a starting point. You can adjust everything later.' })}
            </p>
            {loadingTemplates ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('template.loading', { fallback: 'Loading templates…' })}
              </div>
            ) : (
              (templates || []).map((tpl) => (
                <Button
                  key={tpl.id}
                  variant="outline"
                  className="justify-start h-auto py-3"
                  disabled={creating}
                  onClick={() => handleInstantiate(tpl.id, tpl.name)}
                >
                  <div className="text-left">
                    <div className="font-medium">{tpl.name}</div>
                    {tpl.description && (
                      <div className="text-xs text-muted-foreground mt-0.5">{tpl.description}</div>
                    )}
                  </div>
                </Button>
              ))
            )}
          </div>
        )}

        {step === 'readiness' && (
          <div className="grid gap-2 py-2">
            <p className="text-sm text-muted-foreground">
              {t('readiness.hint', { fallback: 'Checking this assistant before first use.' })}
            </p>
            {checking || !report ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('readiness.checking', { fallback: 'Checking…' })}
              </div>
            ) : (
              report.items.map((item) => (
                <div key={item.dimension} className="flex items-start gap-2 rounded-lg border p-3 text-sm">
                  {item.level === 'ready' ? (
                    <CheckCircle2 className="h-4 w-4 mt-0.5 text-green-600" />
                  ) : item.level === 'warning' ? (
                    <TriangleAlert className="h-4 w-4 mt-0.5 text-amber-600" />
                  ) : (
                    <CircleDashed className="h-4 w-4 mt-0.5 text-destructive" />
                  )}
                  <div>
                    <div className="font-medium">{item.dimension}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{item.reason}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {step === 'verify' && agentId && (
          <div className="grid gap-3 py-2">
            <p className="text-sm text-muted-foreground">
              {t('verify.hint', {
                fallback: 'Send a trial message to confirm everything works.',
                name: agentName,
              })}
            </p>
            <Button
              variant="outline"
              onClick={() => window.open(`/?agent_id=${agentId}`, '_blank', 'noopener,noreferrer')}
            >
              <MessageSquare className="mr-2 h-4 w-4" />
              {t('verify.openChat', { fallback: 'Open a trial chat' })}
            </Button>
          </div>
        )}

        {step === 'done' && (
          <div className="py-2 text-sm text-muted-foreground">
            {t('done.hint', { fallback: 'Setup complete. You can change anything later.' })}
          </div>
        )}

        <DialogFooter className="gap-2">
          {(step === 'template' || step === 'readiness') && (
            <Button variant="ghost" onClick={handleSkip}>
              {t('actions.skip', { fallback: 'Skip' })}
            </Button>
          )}
          {step === 'readiness' && (
            <>
              {isBlocked && (
                <p className="text-xs text-destructive self-center mr-auto">
                  {t('readiness.blockedHint', {
                    fallback: 'Resolve blocked items first, or adjust the configuration.',
                  })}
                </p>
              )}
              <Button variant="outline" disabled={checking || isBlocked} onClick={() => setStep('verify')}>
                {t('actions.continue', { fallback: 'Continue' })}
              </Button>
            </>
          )}
          {step === 'verify' && (
            <Button onClick={() => setStep('done')}>
              {t('actions.finish', { fallback: 'Finish' })}
            </Button>
          )}
          {step === 'done' && <Button onClick={handleFinish}>{t('actions.close', { fallback: 'Close' })}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
