'use client';

/**
 * [INPUT]
 * - @/services/workspaceTrust::previewWorkspaceTrustManifest, decideWorkspaceTrust, type WorkspaceTrustManifest
 * - lucide-react::ShieldAlert, ShieldCheck, Lock, ChevronDown, ChevronUp
 * - @/hooks/shared/useToast::toast
 *
 * [OUTPUT]
 * - WorkspaceTrustBanner: non-blocking top banner for a workspace that needs a trust decision
 *
 * [POS]
 * Displayed at the top of the chat interface in two cases: the folder is restricted and holds extensions that stay
 * off until it is trusted, or the folder is already trusted but lists commands that would run without asking and the user has not seen them yet.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldAlert, ShieldCheck, Lock, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { toast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils/classnameUtils';
import {
  decideWorkspaceTrust,
  previewWorkspaceTrustManifest,
  type WorkspaceTrustLevel,
  type WorkspaceTrustManifest,
} from '@/services/workspaceTrust';
import { shortenHomePath } from '@/lib/directoryBrowseRecent';

export interface WorkspaceTrustBannerProps {
  workspacePath: string | null;
  onTrustChanged?: (level: WorkspaceTrustLevel) => void;
  className?: string;
}

type BannerMode = 'restricted' | 'pending';

const BANNER_COPY = {
  restricted: {
    title: 'restrictedTitle',
    message: 'restrictedMessage',
    action: 'trustAction',
    busy: 'trusting',
    done: 'trusted',
  },
  pending: {
    title: 'pendingTitle',
    message: 'pendingMessage',
    action: 'allowAction',
    busy: 'allowing',
    done: 'commandsAllowed',
  },
} as const satisfies Record<BannerMode, Record<string, string>>;

function resolveBannerMode(manifest: WorkspaceTrustManifest): BannerMode | null {
  if (manifest.current_level === 'TRUSTED') {
    return manifest.pending_command_prefixes.length > 0 ? 'pending' : null;
  }
  return manifest.requires_trust ? 'restricted' : null;
}

interface CommandPrefixListProps {
  label: string;
  prefixes: string[];
}

const CommandPrefixList = ({ label, prefixes }: CommandPrefixListProps) => (
  <div className="mt-2 rounded-md border border-amber-500/20 bg-background/50 p-2 text-xs">
    <p className="font-medium text-foreground">{label}</p>
    <ul aria-label={label} className="mt-1.5 flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
      {prefixes.map((prefix) => (
        <li key={prefix}>
          <Badge variant="outline" className="font-mono text-[10px]">
            {prefix}
          </Badge>
        </li>
      ))}
    </ul>
  </div>
);

export const WorkspaceTrustBanner = memo(({ workspacePath, onTrustChanged, className }: WorkspaceTrustBannerProps) => {
  const t = useTranslations('project.workspaceTrust');
  const [manifest, setManifest] = useState<WorkspaceTrustManifest | null>(null);
  const [loading, setLoading] = useState(false);
  const [trusting, setTrusting] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const loadManifest = useCallback(async () => {
    if (!workspacePath) {
      setManifest(null);
      return;
    }
    setLoading(true);
    try {
      const preview = await previewWorkspaceTrustManifest(workspacePath);
      setManifest(preview);
    } catch {
      setManifest(null);
    } finally {
      setLoading(false);
    }
  }, [workspacePath]);

  useEffect(() => {
    void loadManifest();
  }, [loadManifest]);

  const handleTrust = useCallback(
    async (doneKey: (typeof BANNER_COPY)[BannerMode]['done']) => {
      if (!workspacePath || !manifest) {
        return;
      }
      setTrusting(true);
      try {
        // The hash ties the decision to the list the user is looking at; a folder that changed since then is refused.
        await decideWorkspaceTrust(workspacePath, 'TRUSTED', manifest.manifest_hash);
        toast({ title: t(doneKey) });
        onTrustChanged?.('TRUSTED');
      } catch {
        toast({ title: t('trustFailed'), variant: 'destructive' });
      } finally {
        await loadManifest();
        setTrusting(false);
      }
    },
    [loadManifest, manifest, onTrustChanged, workspacePath, t],
  );

  const mode = manifest ? resolveBannerMode(manifest) : null;
  if (!workspacePath || loading || !manifest || !mode) {
    return null;
  }

  const isRestricted = mode === 'restricted';
  const copy = BANNER_COPY[mode];
  const pendingPrefixes = manifest.pending_command_prefixes;
  const turnedOff: string[] = [];
  if (manifest.skill_count > 0) {
    turnedOff.push(t('itemSkills', { count: manifest.skill_count }));
  }
  if (manifest.mcp_count) {
    turnedOff.push(t('itemMcp', { count: manifest.mcp_count }));
  }
  if (manifest.plugin_count) {
    turnedOff.push(t('itemPlugins', { count: manifest.plugin_count }));
  }
  if (manifest.rule_count > 0) {
    turnedOff.push(t('itemRules', { count: manifest.rule_count }));
  }
  const canExpand = isRestricted && (turnedOff.length > 0 || pendingPrefixes.length > 0);
  const path = shortenHomePath(manifest.path);

  return (
    <aside
      aria-label={t('bannerLabel')}
      className={cn(
        'w-full border-b border-amber-500/20 bg-amber-500/10 px-3 py-2 text-foreground transition-all duration-200',
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400">
            <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          <div className="min-w-0 text-xs">
            <span className="font-semibold text-amber-800 dark:text-amber-300">{t(copy.title)}</span>
            <span className="mx-1.5 text-muted-foreground/60">·</span>
            <span className="break-words text-muted-foreground">{t(copy.message, { path })}</span>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {canExpand && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
              onClick={() => setExpanded((prev) => !prev)}
              aria-expanded={expanded}
            >
              <span>{t('detailsToggle')}</span>
              {expanded ? (
                <ChevronUp className="h-3 w-3" aria-hidden="true" />
              ) : (
                <ChevronDown className="h-3 w-3" aria-hidden="true" />
              )}
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            disabled={trusting}
            className="h-6 gap-1 border-amber-500/30 bg-background/60 px-2.5 text-[11px] font-medium text-amber-800 hover:bg-amber-500/20 dark:text-amber-300"
            onClick={() => void handleTrust(copy.done)}
          >
            <ShieldCheck className="h-3 w-3 text-amber-600 dark:text-amber-400" aria-hidden="true" />
            <span>{t(trusting ? copy.busy : copy.action)}</span>
          </Button>
        </div>
      </div>

      {!isRestricted && <CommandPrefixList label={t('pendingList')} prefixes={pendingPrefixes} />}

      {canExpand && expanded && (
        <>
          {turnedOff.length > 0 && (
            <div className="mt-2 rounded-md border border-amber-500/20 bg-background/50 p-2 text-xs">
              <div className="flex items-center gap-1 font-medium text-foreground">
                <Lock className="h-3 w-3 text-amber-600 dark:text-amber-400" aria-hidden="true" />
                <span>{t('turnedOffTitle')}</span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {turnedOff.map((item) => (
                  <Badge key={item} variant="secondary" className="text-[10px]">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {pendingPrefixes.length > 0 && (
            <CommandPrefixList label={t('commandsOnTrust')} prefixes={pendingPrefixes} />
          )}
        </>
      )}
    </aside>
  );
});

WorkspaceTrustBanner.displayName = 'WorkspaceTrustBanner';

export default WorkspaceTrustBanner;
