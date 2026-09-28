'use client';

/**
 * [INPUT]
 * - @/services/workspaceTrust::previewWorkspaceTrustManifest, decideWorkspaceTrust, type WorkspaceTrustManifest
 * - lucide-react::ShieldAlert, ShieldCheck, ChevronRight, Lock
 * - @/hooks/shared/useToast::toast
 *
 * [OUTPUT]
 * - WorkspaceTrustBanner: non-blocking top banner displayed when workspace is restricted
 *
 * [POS]
 * Displayed at the top of the chat interface when the active workspace is in RESTRICTED mode
 * and contains isolated side-channel extensions (skills, MCPs, rules, plugins).
 */

import { memo, useCallback, useEffect, useState } from 'react';
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

export const WorkspaceTrustBanner = memo(({ workspacePath, onTrustChanged, className }: WorkspaceTrustBannerProps) => {
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

  const handleTrust = useCallback(async () => {
    if (!workspacePath) {
      return;
    }
    setTrusting(true);
    try {
      await decideWorkspaceTrust(workspacePath, 'TRUSTED');
      toast({ title: 'Workspace trusted. Full extensions and tools are now enabled.' });
      onTrustChanged?.('TRUSTED');
      await loadManifest();
    } catch {
      toast({ title: 'Failed to trust workspace', variant: 'destructive' });
    } finally {
      setTrusting(false);
    }
  }, [loadManifest, onTrustChanged, workspacePath]);

  // Only render when the workspace is explicitly restricted and has isolated resources
  if (!workspacePath || loading || !manifest || manifest.current_level === 'TRUSTED' || !manifest.requires_trust) {
    return null;
  }

  const isolatedItems: string[] = [];
  if (manifest.skill_count > 0) {
    isolatedItems.push(`${manifest.skill_count} local skill${manifest.skill_count > 1 ? 's' : ''}`);
  }
  if (manifest.mcp_count && manifest.mcp_count > 0) {
    isolatedItems.push(`${manifest.mcp_count} local MCP server${manifest.mcp_count > 1 ? 's' : ''}`);
  }
  if (manifest.plugin_count && manifest.plugin_count > 0) {
    isolatedItems.push(`${manifest.plugin_count} local plugin${manifest.plugin_count > 1 ? 's' : ''}`);
  }
  if (manifest.rule_count > 0) {
    isolatedItems.push(`${manifest.rule_count} repo rule${manifest.rule_count > 1 ? 's' : ''}`);
  }

  return (
    <aside
      aria-label="Workspace Trust Warning"
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
            <span className="font-semibold text-amber-800 dark:text-amber-300">Restricted Mode</span>
            <span className="mx-1.5 text-muted-foreground/60">·</span>
            <span className="text-muted-foreground">
              Untrusted folder ({shortenHomePath(manifest.path)}). Side-channel scripts isolated.
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {isolatedItems.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
              onClick={() => setExpanded((prev) => !prev)}
              aria-expanded={expanded}
            >
              <span>{isolatedItems.length} isolated</span>
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
            onClick={() => void handleTrust()}
          >
            <ShieldCheck className="h-3 w-3 text-amber-600 dark:text-amber-400" aria-hidden="true" />
            <span>{trusting ? 'Trusting...' : 'Trust Folder'}</span>
          </Button>
        </div>
      </div>

      {expanded && isolatedItems.length > 0 && (
        <div className="mt-2 rounded-md border border-amber-500/20 bg-background/50 p-2 text-xs">
          <div className="flex items-center gap-1 font-medium text-foreground">
            <Lock className="h-3 w-3 text-amber-600 dark:text-amber-400" aria-hidden="true" />
            <span>Isolated Local Resources:</span>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {isolatedItems.map((item) => (
              <Badge key={item} variant="secondary" className="text-[10px]">
                {item}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
});

WorkspaceTrustBanner.displayName = 'WorkspaceTrustBanner';

export default WorkspaceTrustBanner;
