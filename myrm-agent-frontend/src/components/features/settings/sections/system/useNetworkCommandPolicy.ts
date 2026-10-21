import { useState, useCallback } from 'react';
import { toast } from '@/lib/utils/toast';
import { DOMAIN_PATTERN } from './securityPolicyUtils';

export interface UseNetworkCommandPolicyOptions {
  onSave: (overrides: {
    domains?: string[];
    blockedDomains?: string[];
    cmdDenylist?: string[];
    hitl?: boolean;
  }) => void;
  t: (key: string, fallback?: Record<string, string>) => string;
}

export function useNetworkCommandPolicy({ onSave, t }: UseNetworkCommandPolicyOptions) {
  const [networkAllowlist, setNetworkAllowlist] = useState<string[]>([]);
  const [networkBlocklist, setNetworkBlocklist] = useState<string[]>([]);
  const [commandDenylist, setCommandDenylist] = useState<string[]>([]);
  const [domainHitlEnabled, setDomainHitlEnabled] = useState(true);

  const handleAddDomain = useCallback(
    (domain: string) => {
      const raw = domain
        .trim()
        .toLowerCase()
        .replace(/^https?:\/\//, '')
        .replace(/\/.*$/, '');
      if (!raw) {
        return;
      }
      if (!DOMAIN_PATTERN.test(raw)) {
        toast.error(t('domainAllowlist.invalidDomain'));
        return;
      }
      if (networkAllowlist.includes(raw)) {
        toast.error(t('domainAllowlist.duplicateDomain'));
        return;
      }
      const next = [...networkAllowlist, raw];
      setNetworkAllowlist(next);
      onSave({ domains: next });
      toast.success(t('domainAllowlist.domainAdded'));
    },
    [networkAllowlist, onSave, t],
  );

  const handleRemoveDomain = useCallback(
    (idx: number) => {
      const next = networkAllowlist.filter((_, i) => i !== idx);
      setNetworkAllowlist(next);
      onSave({ domains: next });
      toast.success(t('domainAllowlist.domainRemoved'));
    },
    [networkAllowlist, onSave, t],
  );

  const handleAddBlockedDomain = useCallback(
    (domain: string) => {
      const raw = domain
        .trim()
        .toLowerCase()
        .replace(/^https?:\/\//, '')
        .replace(/\/.*$/, '');
      if (!raw) {
        return;
      }
      if (!DOMAIN_PATTERN.test(raw)) {
        toast.error(t('domainBlocklist.invalidDomain'));
        return;
      }
      if (networkBlocklist.includes(raw)) {
        toast.error(t('domainBlocklist.duplicateDomain'));
        return;
      }
      const next = [...networkBlocklist, raw];
      setNetworkBlocklist(next);
      onSave({ blockedDomains: next });
      toast.success(t('domainBlocklist.domainAdded'));
    },
    [networkBlocklist, onSave, t],
  );

  const handleRemoveBlockedDomain = useCallback(
    (idx: number) => {
      const next = networkBlocklist.filter((_, i) => i !== idx);
      setNetworkBlocklist(next);
      onSave({ blockedDomains: next });
      toast.success(t('domainBlocklist.domainRemoved'));
    },
    [networkBlocklist, onSave, t],
  );

  const handleAddCommandPattern = useCallback(
    (pattern: string) => {
      const trimmed = pattern.trim();
      if (!trimmed) {
        return;
      }
      if (!trimmed.includes('*') && !trimmed.includes('?') && !trimmed.includes('[') && trimmed.length < 2) {
        toast.error(t('invalidCommandPattern'));
        return;
      }
      if (commandDenylist.includes(trimmed)) {
        toast.error(t('duplicateCommandPattern'));
        return;
      }
      const next = [...commandDenylist, trimmed];
      setCommandDenylist(next);
      onSave({ cmdDenylist: next });
      toast.success(t('commandPatternAdded'));
    },
    [commandDenylist, onSave, t],
  );

  const handleRemoveCommandPattern = useCallback(
    (idx: number) => {
      const next = commandDenylist.filter((_, i) => i !== idx);
      setCommandDenylist(next);
      onSave({ cmdDenylist: next });
      toast.success(t('commandPatternRemoved'));
    },
    [commandDenylist, onSave, t],
  );

  const handleDomainHitlToggle = useCallback(
    (checked: boolean) => {
      setDomainHitlEnabled(checked);
      onSave({ hitl: checked });
      toast.success(t('domainAllowlist.saved'));
    },
    [onSave, t],
  );

  return {
    networkAllowlist,
    networkBlocklist,
    commandDenylist,
    domainHitlEnabled,
    setNetworkAllowlist,
    setNetworkBlocklist,
    setCommandDenylist,
    setDomainHitlEnabled,
    handleAddDomain,
    handleRemoveDomain,
    handleAddBlockedDomain,
    handleRemoveBlockedDomain,
    handleAddCommandPattern,
    handleRemoveCommandPattern,
    handleDomainHitlToggle,
  };
}
