'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { formatDistanceToNow } from 'date-fns';
import { enUS, zhCN } from 'date-fns/locale';
import { toast } from 'sonner';
import { Copy, KeyRound, Plus, Shield, Trash2 } from 'lucide-react';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Textarea } from '@/components/primitives/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import {
  buildTunnelDockerBuildCommand,
  buildTunnelDockerRunCommand,
} from '@/lib/tunnel-deploy';
import {
  type Tunnel,
  bindTunnelToOrgMcp,
  createTunnel,
  deleteTunnel,
  listTunnels,
  rotateTunnelToken,
} from '@/services/enterprise-org';

interface TunnelDeployContext {
  tunnelId: string;
  upstreamUrl: string;
  authToken: string;
}

interface TunnelAdminPanelProps {
  orgId: string;
}

const TunnelAdminPanel = memo(({ orgId }: TunnelAdminPanelProps) => {
  const t = useTranslations('settings.enterprise');
  const locale = useLocale();
  const dateFnsLocale = useMemo(() => (locale.startsWith('zh') ? zhCN : enUS), [locale]);
  const [tunnels, setTunnels] = useState<Tunnel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [bindingMcp, setBindingMcp] = useState(false);
  const [deployContext, setDeployContext] = useState<TunnelDeployContext | null>(null);

  const [name, setName] = useState('');
  const [upstreamUrl, setUpstreamUrl] = useState('');
  const [upstreamAuth, setUpstreamAuth] = useState('');
  const [description, setDescription] = useState('');

  const loadTunnels = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listTunnels(orgId);
      setTunnels(data);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('tunnelLoadFailed'));
    } finally {
      setLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void loadTunnels();
  }, [loadTunnels]);

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !upstreamUrl.trim()) return;
    try {
      setSaving(true);
      const upstreamHeaders = upstreamAuth.trim()
        ? { Authorization: upstreamAuth.trim() }
        : undefined;
      const result = await createTunnel(orgId, {
        name: name.trim(),
        upstream_url: upstreamUrl.trim(),
        description: description.trim(),
        upstream_headers: upstreamHeaders,
      });
      setDeployContext({
        tunnelId: result.tunnel.id,
        upstreamUrl: result.tunnel.upstream_url,
        authToken: result.auth_token,
      });
      setShowCreate(false);
      setName('');
      setUpstreamUrl('');
      setUpstreamAuth('');
      setDescription('');
      await loadTunnels();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('tunnelCreateFailed'));
    } finally {
      setSaving(false);
    }
  }, [orgId, name, upstreamUrl, upstreamAuth, description, t, loadTunnels]);

  const handleBindOrgMcp = useCallback(async () => {
    if (!deployContext) return;
    try {
      setBindingMcp(true);
      await bindTunnelToOrgMcp(orgId, deployContext.tunnelId);
      toast.success(t('tunnelBindMcpSuccess'));
      setDeployContext(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('tunnelBindMcpFailed'));
    } finally {
      setBindingMcp(false);
    }
  }, [orgId, deployContext, t]);

  const handleDelete = useCallback(
    async (tunnel: Tunnel) => {
      try {
        await deleteTunnel(orgId, tunnel.id);
        toast.success(t('tunnelDeleted'));
        await loadTunnels();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : t('tunnelDeleteFailed'));
      }
    },
    [orgId, t, loadTunnels],
  );

  const handleRotate = useCallback(
    async (tunnel: Tunnel) => {
      try {
        const result = await rotateTunnelToken(orgId, tunnel.id);
        setDeployContext({
          tunnelId: result.tunnel.id,
          upstreamUrl: result.tunnel.upstream_url,
          authToken: result.auth_token,
        });
        await loadTunnels();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : t('tunnelRotateFailed'));
      }
    },
    [orgId, t, loadTunnels],
  );

  const dockerBuildCommand = buildTunnelDockerBuildCommand();
  const dockerRunCommand = deployContext
    ? buildTunnelDockerRunCommand(deployContext)
    : '';

  const copyToken = useCallback(() => {
    if (deployContext) {
      void navigator.clipboard.writeText(deployContext.authToken);
      toast.success(t('tunnelTokenCopied'));
    }
  }, [deployContext, t]);

  const copyDockerBuild = useCallback(() => {
    void navigator.clipboard.writeText(dockerBuildCommand);
    toast.success(t('tunnelDockerBuildCopied'));
  }, [dockerBuildCommand, t]);

  const copyDockerRun = useCallback(() => {
    if (dockerRunCommand) {
      void navigator.clipboard.writeText(dockerRunCommand);
      toast.success(t('tunnelDockerRunCopied'));
    }
  }, [dockerRunCommand, t]);

  return (
    <>
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            {t('tunnelTitle')}
          </span>
        }
        description={t('tunnelDescription')}
        action={
          <Button size="sm" variant="outline" onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4 mr-1" />
            {t('tunnelAdd')}
          </Button>
        }
      >
        {loading ? (
          <div className="animate-pulse space-y-2">
            <div className="h-14 bg-muted rounded-lg" />
          </div>
        ) : tunnels.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">{t('tunnelEmpty')}</p>
        ) : (
          <div className="space-y-2">
            {tunnels.map((tunnel) => (
              <div
                key={tunnel.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-3 px-4 rounded-lg border border-border/40 bg-background/50"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-sm">{tunnel.name}</span>
                    <Badge
                      variant={
                        tunnel.status === 'online'
                          ? 'default'
                          : tunnel.status === 'degraded'
                            ? 'secondary'
                            : 'outline'
                      }
                      className="text-xs"
                    >
                      {tunnel.status === 'online'
                        ? t('tunnelOnline')
                        : tunnel.status === 'degraded'
                          ? t('tunnelDegraded')
                          : t('tunnelOffline')}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{tunnel.upstream_url}</p>
                  {tunnel.description && (
                    <p className="text-xs text-muted-foreground">{tunnel.description}</p>
                  )}
                  {tunnel.status === 'degraded' && tunnel.last_upstream_error && (
                    <p className="text-xs text-destructive/90 break-words">
                      {t('tunnelLastUpstreamError', { error: tunnel.last_upstream_error })}
                    </p>
                  )}
                  {tunnel.status === 'degraded' && tunnel.last_error_at != null && (
                    <p className="text-xs text-muted-foreground">
                      {t('tunnelLastErrorAt', {
                        time: formatDistanceToNow(new Date(tunnel.last_error_at * 1000), {
                          addSuffix: true,
                          locale: dateFnsLocale,
                        }),
                      })}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void handleRotate(tunnel)}
                    title={t('tunnelRotateToken')}
                  >
                    <KeyRound className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={() => void handleDelete(tunnel)}
                    title={t('tunnelDelete')}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </SettingsSection>

      {/* Create Tunnel Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('tunnelAdd')}</DialogTitle>
            <DialogDescription>{t('tunnelAddDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>{t('tunnelName')}</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="internal-crm-mcp"
              />
            </div>
            <div className="space-y-2">
              <Label>{t('tunnelUpstreamUrl')}</Label>
              <Input
                value={upstreamUrl}
                onChange={(e) => setUpstreamUrl(e.target.value)}
                placeholder="http://host.docker.internal:8080/mcp"
              />
            </div>
            <div className="space-y-2">
              <Label>{t('tunnelUpstreamAuthLabel')}</Label>
              <Input
                value={upstreamAuth}
                onChange={(e) => setUpstreamAuth(e.target.value)}
                placeholder={t('tunnelUpstreamAuthPlaceholder')}
                type="password"
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">{t('tunnelUpstreamAuthHint')}</p>
            </div>
            <div className="space-y-2">
              <Label>{t('mcpServerDescription')}</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('mcpServerDescriptionPlaceholder')}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              {t('cancel')}
            </Button>
            <Button
              onClick={() => void handleCreate()}
              disabled={saving || !name.trim() || !upstreamUrl.trim()}
            >
              {t('confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Token Display Dialog */}
      <Dialog open={deployContext !== null} onOpenChange={() => setDeployContext(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('tunnelTokenTitle')}</DialogTitle>
            <DialogDescription>{t('tunnelTokenDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-2">
              <Label>{t('tunnelAuthTokenLabel')}</Label>
              <div className="flex items-center gap-2">
                <Input value={deployContext?.authToken ?? ''} readOnly className="font-mono text-xs" />
                <Button size="sm" variant="outline" onClick={copyToken} title={t('tunnelTokenCopied')}>
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t('tunnelDockerBuildLabel')}</Label>
              <p className="text-xs text-muted-foreground">{t('tunnelDockerBuildDesc')}</p>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-start gap-2">
                <Textarea
                  readOnly
                  value={dockerBuildCommand}
                  rows={2}
                  className="font-mono text-xs bg-muted/40 resize-none min-h-[56px]"
                />
                <Button
                  size="sm"
                  variant="outline"
                  className="shrink-0"
                  onClick={copyDockerBuild}
                  title={t('tunnelDockerBuildCopied')}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t('tunnelDockerRunLabel')}</Label>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-start gap-2">
                <Textarea
                  readOnly
                  value={dockerRunCommand}
                  rows={6}
                  className="font-mono text-xs bg-muted/40 resize-none min-h-[120px]"
                />
                <Button
                  size="sm"
                  variant="outline"
                  className="shrink-0"
                  onClick={copyDockerRun}
                  title={t('tunnelDockerRunCopied')}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <p className="text-xs text-destructive font-medium">{t('tunnelTokenWarning')}</p>
          </div>
          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button
              variant="secondary"
              className="w-full sm:w-auto"
              disabled={bindingMcp}
              onClick={() => void handleBindOrgMcp()}
            >
              {t('tunnelBindMcp')}
            </Button>
            <Button className="w-full sm:w-auto" onClick={() => setDeployContext(null)}>
              {t('confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
});

TunnelAdminPanel.displayName = 'TunnelAdminPanel';

export default TunnelAdminPanel;
