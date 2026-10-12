'use client';

import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconShield,
  IconShieldCheck,
  IconLock,
  IconFolder,
  IconCheck,
  IconAlertTriangle,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import SettingsSection from '../SettingsSection';

interface SandboxLeastPrivilegeCardProps {
  onScrollToTrustedFolders?: () => void;
  onScrollToMatrix?: () => void;
}

export const SandboxLeastPrivilegeCard = memo(({
  onScrollToTrustedFolders,
  onScrollToMatrix,
}: SandboxLeastPrivilegeCardProps) => {
  const t = useTranslations('settings.securityPolicy');

  const handleJumpToFolders = useCallback(() => {
    if (onScrollToTrustedFolders) {
      onScrollToTrustedFolders();
      return;
    }
    const el = document.getElementById('trusted-folders-section');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  }, [onScrollToTrustedFolders]);

  const handleJumpToMatrix = useCallback(() => {
    if (onScrollToMatrix) {
      onScrollToMatrix();
      return;
    }
    const el = document.getElementById('capability-matrix-section');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  }, [onScrollToMatrix]);

  return (
    <SettingsSection
      title={t('leastPrivilege.title', {
        default: 'Least Privilege & Sandbox Guard (Default Stance)',
      })}
      description={t('leastPrivilege.description', {
        default:
          'Firm commitment to default least-privilege boundaries and physical sandbox isolation — avoiding destructive "full access" risks.',
      })}
    >
      <div className="space-y-4 rounded-xl border border-border bg-card/60 p-5 shadow-sm">
        {/* Header stance banner */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <IconShield className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-foreground">
                  {t('leastPrivilege.stanceHeader', {
                    default: 'Default Least Privilege Posture Active',
                  })}
                </span>
                <Badge variant="outline" className="border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400">
                  <IconCheck className="mr-1 h-3 w-3" />
                  {t('leastPrivilege.activeBadge', { default: 'Protected' })}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {t('leastPrivilege.stanceSummary', {
                  default:
                    'All commands and mutations require explicit Approval FSM confirmation or physical sandbox execution.',
                })}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Button size="sm" variant="outline" onClick={handleJumpToFolders}>
              <IconFolder className="mr-1.5 h-3.5 w-3.5 text-muted-foreground" />
              {t('leastPrivilege.manageTrustBtn', { default: 'Trusted Folders' })}
            </Button>
            <Button size="sm" variant="secondary" onClick={handleJumpToMatrix}>
              <IconLock className="mr-1.5 h-3.5 w-3.5 text-muted-foreground" />
              {t('leastPrivilege.viewMatrixBtn', { default: 'Matrix Posture' })}
            </Button>
          </div>
        </div>

        {/* Contrast with WorkBuddy anti-pattern */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 pt-2">
          <div className="rounded-lg border border-border/80 bg-background/80 p-3.5 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
              <IconShieldCheck className="h-4 w-4 text-primary" />
              <span>
                {t('leastPrivilege.myrmWayTitle', {
                  default: 'Myrm Clean Approval & Sandbox Strategy',
                })}
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('leastPrivilege.myrmWayDesc', {
                default:
                  'Unified ApprovalContract + interrupt state machine. High-risk operations (e.g. .env, PEM keys, fork bombs) are stopped by physical sandbox firewalls, while routine tasks run smoothly.',
              })}
            </p>
          </div>

          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3.5 space-y-1.5">
            <div className="flex items-center gap-2 text-xs font-semibold text-amber-700 dark:text-amber-400">
              <IconAlertTriangle className="h-4 w-4 text-amber-600" />
              <span>
                {t('leastPrivilege.antiPatternTitle', {
                  default: 'Why "Full Access" Is Rejected',
                })}
              </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('leastPrivilege.antiPatternDesc', {
                default:
                  'Competitor "Full Access" leaves local files and host credentials exposed to arbitrary exfiltration. We preserve least-privilege boundaries without awkward evasion loops.',
              })}
            </p>
          </div>
        </div>
      </div>
    </SettingsSection>
  );
});

SandboxLeastPrivilegeCard.displayName = 'SandboxLeastPrivilegeCard';
