'use client';

/**
 * Granular ACL Configuration Drawer Component for memory assets.
 *
 * [INPUT] asset: MemoryAsset | null, isOpen: boolean, onClose: () => void, onSaveAcl
 * [OUTPUT] AssetAclDrawer: Modal drawer to configure Private, Team, or Project scopes and authorized agents.
 * [POS] src/components/features/memory-hub/AssetAclDrawer.tsx
 */

import { memo, useState, useEffect } from 'react';
import {
  ShieldAlert,
  Users,
  FolderGit2,
  X,
  Save,
  Shield,
  Key,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { AclScope, AclUpdatePayload, MemoryAsset } from './memoryHubTypes';

export interface AssetAclDrawerProps {
  asset: MemoryAsset | null;
  isOpen: boolean;
  onClose: () => void;
  onSaveAcl: (assetId: string, payload: AclUpdatePayload) => void;
  className?: string;
}

const SCOPE_OPTIONS: Array<{
  key: AclScope;
  labelKey: string;
  descKey: string;
  defaultLabel: string;
  defaultDesc: string;
  icon: typeof ShieldAlert;
}> = [
  {
    key: 'team',
    labelKey: 'aclTeam',
    descKey: 'aclTeamDesc',
    defaultLabel: 'Team Shared',
    defaultDesc: 'Accessible and mountable by all agents in the current workspace.',
    icon: Users,
  },
  {
    key: 'private',
    labelKey: 'aclPrivate',
    descKey: 'aclPrivateDesc',
    defaultLabel: 'Private Enclave',
    defaultDesc: 'Strictly restricted to the owner agent and explicit allowed agent list.',
    icon: ShieldAlert,
  },
  {
    key: 'project',
    labelKey: 'aclProject',
    descKey: 'aclProjectDesc',
    defaultLabel: 'Project Bound',
    defaultDesc: 'Bounded exclusively to the active code repository and sandbox volume.',
    icon: FolderGit2,
  },
];

export const AssetAclDrawer = memo(function AssetAclDrawer({
  asset,
  isOpen,
  onClose,
  onSaveAcl,
  className,
}: AssetAclDrawerProps) {
  const t = useTranslations('memoryHub');

  const [selectedScope, setSelectedScope] = useState<AclScope>('team');
  const [allowedAgentsInput, setAllowedAgentsInput] = useState('');

  useEffect(() => {
    if (asset) {
      setSelectedScope(asset.acl_scope);
      setAllowedAgentsInput((asset.allowed_agent_ids || []).join(', '));
    }
  }, [asset]);

  if (!isOpen || !asset) {
    return null;
  }

  const handleSave = () => {
    const agentList = allowedAgentsInput
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    onSaveAcl(asset.id, {
      acl_scope: selectedScope,
      allowed_agent_ids: agentList,
    });
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150"
      data-testid="asset-acl-drawer"
    >
      <div
        className={cn(
          'w-full max-w-md rounded-2xl border border-border bg-background shadow-2xl overflow-hidden flex flex-col text-foreground',
          className,
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/80 bg-muted/20">
          <div className="flex items-center gap-2">
            <div className="p-1 rounded-md bg-primary/10 text-primary">
              <Shield className="h-4 w-4" />
            </div>
            <div>
              <h3 className="font-semibold text-xs">
                {t('aclDrawerTitle') || 'Granular ACL Security Policy'}
              </h3>
              <p className="text-[10px] text-muted-foreground truncate max-w-[280px]">
                {asset.name}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-4 flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
              <Key className="h-3.5 w-3.5 text-primary" />
              <span>{t('selectAclScope') || 'Access Scope Isolation'}</span>
            </label>

            <div className="flex flex-col gap-2">
              {SCOPE_OPTIONS.map((opt) => {
                const isSelected = selectedScope === opt.key;
                const Icon = opt.icon;
                return (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => {
                      setSelectedScope(opt.key);
                    }}
                    className={cn(
                      'flex items-start gap-3 p-3 rounded-xl border text-left transition-all',
                      isSelected
                        ? 'border-primary/60 bg-primary/5 ring-1 ring-primary/20'
                        : 'border-border/60 hover:bg-muted/40 hover:border-border',
                    )}
                    data-testid={`scope-opt-${opt.key}`}
                  >
                    <div
                      className={cn(
                        'p-2 rounded-lg mt-0.5',
                        isSelected
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted text-muted-foreground',
                      )}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-xs text-foreground">
                        {t(opt.labelKey) || opt.defaultLabel}
                      </div>
                      <div className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                        {t(opt.descKey) || opt.defaultDesc}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Additional input for Private scope: allowed agents list */}
          {selectedScope === 'private' && (
            <div className="flex flex-col gap-1.5 pt-1">
              <label className="text-xs font-medium text-muted-foreground">
                {t('authorizedAgentsLabel') || 'Explicit Authorized Agent IDs (comma separated)'}
              </label>
              <input
                type="text"
                value={allowedAgentsInput}
                onChange={(e) => {
                  setAllowedAgentsInput(e.target.value);
                }}
                placeholder="agent-security, agent-auditor..."
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary/50 text-foreground font-mono"
                data-testid="allowed-agents-input"
              />
              <span className="text-[10px] text-muted-foreground">
                {t('ownerAutoAuthorized') || 'The owner agent is always granted full access automatically.'}
              </span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border/80 bg-muted/20">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            {t('cancel') || 'Cancel'}
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs transition-all"
            data-testid="save-acl-btn"
          >
            <Save className="h-3.5 w-3.5" />
            <span>{t('saveAclPolicy') || 'Save ACL Policy'}</span>
          </button>
        </div>
      </div>
    </div>
  );
});
