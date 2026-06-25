import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from '@/hooks/useToast';
import {
  getSkillFile,
  getSkillEnvVars,
  updateSkillEnvVars,
  trustSkill,
  untrustSkill,
  toggleEvolutionLock,
  revealSkill,
} from '@/services/skill';
import type { Skill } from '@/store/skill/types';

interface UseSkillDetailSheetParams {
  skill: Skill | null;
  open: boolean;
  isEnabled: boolean;
  onOpenChange: (open: boolean) => void;
  onToggle?: (skillId: string) => Promise<void>;
  onDelete?: (skill: Skill) => Promise<void>;
  onTrustChange?: () => void;
  t: (key: string, fallbackOrParams?: string | Record<string, unknown>) => string;
}

export function useSkillDetailSheet({
  skill,
  open,
  isEnabled,
  onOpenChange,
  onToggle,
  onDelete,
  onTrustChange,
  t,
}: UseSkillDetailSheetParams) {
  const [skillContent, setSkillContent] = useState<string>('');
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [isToggling, setIsToggling] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showTrustConfirm, setShowTrustConfirm] = useState(false);
  const [isTrusting, setIsTrusting] = useState(false);
  const [showOptimizeInput, setShowOptimizeInput] = useState(false);
  const [optimizeInstruction, setOptimizeInstruction] = useState('');
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [isEvolutionLocked, setIsEvolutionLocked] = useState(false);
  const [isTogglingLock, setIsTogglingLock] = useState(false);
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [isPathInvalid, setIsPathInvalid] = useState(false);
  const [isRevealing, setIsRevealing] = useState(false);

  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [envVarsDirty, setEnvVarsDirty] = useState(false);
  const [isSavingEnv, setIsSavingEnv] = useState(false);

  const hasRequirements = useMemo(() => {
    if (!skill) return false;
    const { bins, env, config } = skill.requires;
    return bins.length > 0 || env.length > 0 || config.length > 0;
  }, [skill]);

  const hasEnvRequirements = useMemo(() => (skill?.requires.env.length ?? 0) > 0 || !!skill?.primary_env, [skill]);

  useEffect(() => {
    if (skill && open) {
      setIsEvolutionLocked(skill.evolution_locked);
      setIsLoadingContent(true);
      getSkillFile(skill.id, 'SKILL.md')
        .then(setSkillContent)
        .catch(() => setSkillContent(''))
        .finally(() => setIsLoadingContent(false));

      if (skill.requires.env.length > 0 || skill.primary_env) {
        getSkillEnvVars(skill.id)
          .then((res) => {
            setEnvVars(res.env_vars);
            setEnvVarsDirty(false);
          })
          .catch(() => setEnvVars({}));
      } else {
        setEnvVars({});
        setEnvVarsDirty(false);
      }
    }
  }, [skill, open]);

  const handleToggle = useCallback(async () => {
    if (!skill || !onToggle) return;
    setIsToggling(true);
    try {
      await onToggle(skill.id);
      toast({
        title: isEnabled ? t('detail.disableSuccess') : t('detail.enableSuccess'),
        description: isEnabled
          ? t('detail.disableSuccessDesc', { name: skill.name })
          : t('detail.enableSuccessDesc', { name: skill.name }),
      });
    } catch {
      toast({ title: t('detail.toggleFailed'), variant: 'destructive' });
    } finally {
      setIsToggling(false);
    }
  }, [skill, onToggle, isEnabled, t]);

  const handleDelete = useCallback(async () => {
    if (!skill || !onDelete) return;
    setIsDeleting(true);
    try {
      await onDelete(skill);
      toast({
        title: t('detail.deleteSuccess'),
        description: t('detail.deleteSuccessDesc', { name: skill.name }),
      });
      onOpenChange(false);
    } catch {
      toast({ title: t('detail.deleteFailed'), variant: 'destructive' });
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  }, [skill, onDelete, onOpenChange, t]);

  const handleEnvVarChange = useCallback((key: string, value: string) => {
    setEnvVars((prev) => ({ ...prev, [key]: value }));
    setEnvVarsDirty(true);
  }, []);

  const handleSaveEnvVars = useCallback(async () => {
    if (!skill) return;
    setIsSavingEnv(true);
    try {
      await updateSkillEnvVars(skill.id, envVars);
      setEnvVarsDirty(false);
      toast({ title: t('card.keysSaved') });
    } catch {
      toast({ title: t('card.keysSaveFailed'), variant: 'destructive' });
    } finally {
      setIsSavingEnv(false);
    }
  }, [skill, envVars, t]);

  const isUserTrustable = skill?.trust === 'installed' && skill?.type !== 'local';
  const isUserTrusted = !!skill?.user_trusted;

  const handleTrust = useCallback(async () => {
    if (!skill) return;
    setIsTrusting(true);
    try {
      await trustSkill(skill.id);
      toast({
        title: t('card.trustSuccess'),
        description: t('card.trustSuccessDesc', { name: skill.name }),
      });
      onTrustChange?.();
      onOpenChange(false);
    } catch {
      toast({ title: t('card.trustFailed'), variant: 'destructive' });
    } finally {
      setIsTrusting(false);
      setShowTrustConfirm(false);
    }
  }, [skill, t, onOpenChange, onTrustChange]);

  const handleUntrust = useCallback(async () => {
    if (!skill) return;
    setIsTrusting(true);
    try {
      await untrustSkill(skill.id);
      toast({
        title: t('card.untrustSuccess'),
        description: t('card.untrustSuccessDesc', { name: skill.name }),
      });
      onTrustChange?.();
      onOpenChange(false);
    } catch {
      toast({ title: t('card.trustFailed'), variant: 'destructive' });
    } finally {
      setIsTrusting(false);
    }
  }, [skill, t, onOpenChange, onTrustChange]);

  const reloadSkillContent = useCallback(() => {
    if (!skill) return;
    getSkillFile(skill.id, 'SKILL.md')
      .then(setSkillContent)
      .catch(() => setSkillContent(''));
  }, [skill]);

  const handleReveal = useCallback(async () => {
    if (!skill) return;
    setIsRevealing(true);
    try {
      await revealSkill(skill.id);
      setIsPathInvalid(false);
    } catch (error: unknown) {
      const err = error as { status?: number; message?: string };
      if (err?.status === 404 || err?.message?.includes('404')) {
        setIsPathInvalid(true);
        toast({ title: t('detail.pathInvalid', 'Path is invalid or deleted'), variant: 'destructive' });
      } else {
        toast({ title: t('detail.revealFailed', 'Failed to reveal path'), variant: 'destructive' });
      }
    } finally {
      setIsRevealing(false);
    }
  }, [skill, t]);

  const handleToggleEvolutionLock = useCallback(async () => {
    if (!skill) return;
    const newLocked = !isEvolutionLocked;
    setIsTogglingLock(true);
    try {
      await toggleEvolutionLock(skill.id, newLocked);
      setIsEvolutionLocked(newLocked);
      toast({
        title: newLocked ? t('detail.evolutionLocked') : t('detail.evolutionUnlocked'),
        description: newLocked
          ? t('detail.evolutionLockedDesc', { name: skill.name })
          : t('detail.evolutionUnlockedDesc', { name: skill.name }),
      });
    } catch {
      toast({ title: t('detail.evolutionLockFailed'), variant: 'destructive' });
    } finally {
      setIsTogglingLock(false);
    }
  }, [skill, isEvolutionLocked, t]);

  const handleOptimize = useCallback(async () => {
    if (!skill || !optimizeInstruction.trim()) return;
    setIsOptimizing(true);
    try {
      const response = await fetch(`/api/v1/evolution/derive/${skill.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: optimizeInstruction.trim() }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to start optimization');
      }
      toast({
        title: t('detail.optimizeStarted'),
        description: t('detail.optimizeStartedDesc', { name: skill.name }),
      });
      setShowOptimizeInput(false);
      setOptimizeInstruction('');
    } catch (error) {
      toast({
        title: t('detail.optimizeFailed'),
        description: error instanceof Error ? error.message : t('detail.optimizeFailed'),
        variant: 'destructive',
      });
    } finally {
      setIsOptimizing(false);
    }
  }, [skill, optimizeInstruction]);

  return {
    skillContent,
    isLoadingContent,
    isToggling,
    isDeleting,
    showDeleteConfirm,
    setShowDeleteConfirm,
    showTrustConfirm,
    setShowTrustConfirm,
    isTrusting,
    showOptimizeInput,
    setShowOptimizeInput,
    optimizeInstruction,
    setOptimizeInstruction,
    isOptimizing,
    isEvolutionLocked,
    isTogglingLock,
    showExportDialog,
    setShowExportDialog,
    isPathInvalid,
    isRevealing,
    envVars,
    envVarsDirty,
    isSavingEnv,
    hasRequirements,
    hasEnvRequirements,
    isUserTrustable,
    isUserTrusted,
    handleToggle,
    handleDelete,
    handleEnvVarChange,
    handleSaveEnvVars,
    handleTrust,
    handleUntrust,
    reloadSkillContent,
    handleReveal,
    handleToggleEvolutionLock,
    handleOptimize,
  };
}
