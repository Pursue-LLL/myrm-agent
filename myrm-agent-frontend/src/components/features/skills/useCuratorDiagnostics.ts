import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import {
  getSkillDiagnostics,
  remediateSkillFinding,
  type SkillDoctorDiagnosticsResponse,
  type SkillRemediationAction,
} from '@/services/skill';

/** Holds the skill doctor report and runs one remediation at a time (a call made while another runs is ignored), reporting each outcome as a toast. */
export function useCuratorDiagnostics(onRemediated?: () => void) {
  const t = useTranslations('settings.skills.curator');
  const [diagnostics, setDiagnostics] = useState<SkillDoctorDiagnosticsResponse | null>(null);
  const [remediatingSkill, setRemediatingSkill] = useState<string | null>(null);
  const inFlight = useRef(false);

  const loadDiagnostics = useCallback(async () => {
    try {
      setDiagnostics(await getSkillDiagnostics());
    } catch {
      setDiagnostics(null);
    }
  }, []);

  const remediate = useCallback(
    async (skillName: string, action: SkillRemediationAction) => {
      if (inFlight.current) {
        return;
      }
      inFlight.current = true;
      setRemediatingSkill(skillName);
      try {
        const res = await remediateSkillFinding(skillName, action);
        if (res.success) {
          toast({
            title: t('doctor.remediateSuccessTitle'),
            description: t('doctor.remediateSuccessDesc', { name: skillName }),
          });
          await loadDiagnostics();
          onRemediated?.();
        } else {
          toast({
            title: t('doctor.remediateFailedTitle'),
            description: res.error || t('doctor.remediateFailedDesc'),
            variant: 'destructive',
          });
        }
      } catch (err: unknown) {
        toast({
          title: t('doctor.remediateFailedTitle'),
          description: err instanceof Error ? err.message : t('doctor.remediateFailedDesc'),
          variant: 'destructive',
        });
      } finally {
        inFlight.current = false;
        setRemediatingSkill(null);
      }
    },
    [t, loadDiagnostics, onRemediated],
  );

  return { diagnostics, remediatingSkill, loadDiagnostics, remediate };
}
