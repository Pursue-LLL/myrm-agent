/**
 * [INPUT] ./agentSecurityOverrides::SecurityOverridesData, normalizeDomainInput (POS: 安全覆盖数据), ../../system/securityPolicyUtils::DOMAIN_PATTERN (POS: 域名格式校验)
 * [OUTPUT] useSecurityListEditors: 允许路径、域名白名单、域名黑名单、命令拒绝列表四个编辑器的输入状态、校验与增删动作
 * [POS] AgentSecurityTab 的列表编辑逻辑层；黑名单与命令列表在输入变化时清除上一次的校验错误，新增时校验格式与重复。
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { DOMAIN_PATTERN } from '../../system/securityPolicyUtils';
import { normalizeDomainInput, type SecurityOverridesData } from './agentSecurityOverrides';

export interface ListEditorBinding {
  items: string[];
  value: string;
  onValueChange: (value: string) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
  error?: string | null;
}

interface UseSecurityListEditorsParams {
  data: SecurityOverridesData;
  update: (patch: Partial<SecurityOverridesData>) => void;
}

export function useSecurityListEditors({ data, update }: UseSecurityListEditorsParams) {
  const t = useTranslations('agent.security');
  const [newPath, setNewPath] = useState('');
  const [newDomain, setNewDomain] = useState('');
  const [newBlockedDomain, setNewBlockedDomain] = useState('');
  const [newCommandPattern, setNewCommandPattern] = useState('');
  const [blocklistError, setBlocklistError] = useState<string | null>(null);
  const [cmdDenylistError, setCmdDenylistError] = useState<string | null>(null);

  const addRoot = useCallback(() => {
    const trimmed = newPath.trim();
    if (!trimmed || data.allowedRoots.includes(trimmed)) {
      return;
    }
    update({ allowedRoots: [...data.allowedRoots, trimmed] });
    setNewPath('');
  }, [newPath, data.allowedRoots, update]);

  const removeRoot = useCallback(
    (idx: number) => {
      update({ allowedRoots: data.allowedRoots.filter((_, i) => i !== idx) });
    },
    [data.allowedRoots, update],
  );

  const addDomain = useCallback(() => {
    const trimmed = newDomain.trim().toLowerCase();
    if (!trimmed || data.networkAllowlist.includes(trimmed)) {
      return;
    }
    update({ networkAllowlist: [...data.networkAllowlist, trimmed] });
    setNewDomain('');
  }, [newDomain, data.networkAllowlist, update]);

  const removeDomain = useCallback(
    (idx: number) => {
      update({ networkAllowlist: data.networkAllowlist.filter((_, i) => i !== idx) });
    },
    [data.networkAllowlist, update],
  );

  const addBlockedDomain = useCallback(() => {
    const normalized = normalizeDomainInput(newBlockedDomain);
    if (!normalized) {
      return;
    }
    if (!DOMAIN_PATTERN.test(normalized)) {
      setBlocklistError(t('invalidBlockedDomain'));
      return;
    }
    if (data.networkBlocklist.includes(normalized)) {
      setBlocklistError(t('duplicateBlockedDomain'));
      return;
    }
    setBlocklistError(null);
    update({ networkBlocklist: [...data.networkBlocklist, normalized] });
    setNewBlockedDomain('');
  }, [newBlockedDomain, data.networkBlocklist, update, t]);

  const removeBlockedDomain = useCallback(
    (idx: number) => {
      setBlocklistError(null);
      update({ networkBlocklist: data.networkBlocklist.filter((_, i) => i !== idx) });
    },
    [data.networkBlocklist, update],
  );

  const addCommandPattern = useCallback(() => {
    const trimmed = newCommandPattern.trim();
    if (!trimmed) {
      return;
    }
    if (data.commandDenylist.includes(trimmed)) {
      setCmdDenylistError(t('duplicateCommandPattern'));
      return;
    }
    setCmdDenylistError(null);
    update({ commandDenylist: [...data.commandDenylist, trimmed] });
    setNewCommandPattern('');
  }, [newCommandPattern, data.commandDenylist, update, t]);

  const removeCommandPattern = useCallback(
    (idx: number) => {
      setCmdDenylistError(null);
      update({ commandDenylist: data.commandDenylist.filter((_, i) => i !== idx) });
    },
    [data.commandDenylist, update],
  );

  const roots: ListEditorBinding = {
    items: data.allowedRoots,
    value: newPath,
    onValueChange: setNewPath,
    onAdd: addRoot,
    onRemove: removeRoot,
  };
  const allowlist: ListEditorBinding = {
    items: data.networkAllowlist,
    value: newDomain,
    onValueChange: setNewDomain,
    onAdd: addDomain,
    onRemove: removeDomain,
  };
  const blocklist: ListEditorBinding = {
    items: data.networkBlocklist,
    value: newBlockedDomain,
    onValueChange: (next) => {
      setNewBlockedDomain(next);
      if (blocklistError) {
        setBlocklistError(null);
      }
    },
    onAdd: addBlockedDomain,
    onRemove: removeBlockedDomain,
    error: blocklistError,
  };
  const denylist: ListEditorBinding = {
    items: data.commandDenylist,
    value: newCommandPattern,
    onValueChange: (next) => {
      setNewCommandPattern(next);
      if (cmdDenylistError) {
        setCmdDenylistError(null);
      }
    },
    onAdd: addCommandPattern,
    onRemove: removeCommandPattern,
    error: cmdDenylistError,
  };

  return { roots, allowlist, blocklist, denylist };
}
