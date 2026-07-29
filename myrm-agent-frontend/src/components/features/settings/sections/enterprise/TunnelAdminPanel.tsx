'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Copy, KeyRound, Plus, Shield, Trash2 } from 'lucide-react';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import {
  type Tunnel,
  createTunnel,
  deleteTunnel,
  listTunnels,
  rotateTunnelToken,
} from '@/services/enterprise-org';

interface TunnelAdminPanelProps {
  orgId: string;
}

const TunnelAdminPanel = memo(({ orgId }: TunnelAdminPanelProps) => {
  const t = useTranslations('settings.enterprise');
  const [tunnels, setTunnels] = useState<Tunnel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newToken, setNewToken] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [upstreamUrl, setUpstreamUrl] = useState('');
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
      const result = await createTunnel(orgId, {
        name: name.trim(),
        upstream_url: upstreamUrl.trim(),
        description: description.trim(),
      });
      setNewToken(result.auth_token);
      setShowCreate(false);
      setName('');
      setUpstreamUrl('');
      setDescription('');
      await loadTunnels();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('tunnelCreateFailed'));
    } finally {
      setSaving(false);
    }
  }, [orgId, name, upstreamUrl, description, t, loadTunnels]);

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
        setNewToken(result.auth_token);
        await loadTunnels();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : t('tunnelRotateFailed'));
      }
    },
    [orgId, t, loadTunnels],
  );

  const copyToken = useCallback(() => {
    if (newToken) {
      void navigator.clipboard.writeText(newToken);
      toast.success(t('tunnelTokenCopied'));
    }
  }, [newToken, t]);

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
                      variant={tunnel.status === 'online' ? 'default' : 'outline'}
                      className="text-xs"
                    >
                      {tunnel.status === 'online' ? t('tunnelOnline') : t('tunnelOffline')}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{tunnel.upstream_url}</p>
                  {tunnel.description && (
                    <p className="text-xs text-muted-foreground">{tunnel.description}</p>
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
                placeholder="http://localhost:8080/mcp"
              />
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
      <Dialog open={newToken !== null} onOpenChange={() => setNewToken(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('tunnelTokenTitle')}</DialogTitle>
            <DialogDescription>{t('tunnelTokenDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-2">
              <Input value={newToken ?? ''} readOnly className="font-mono text-xs" />
              <Button size="sm" variant="outline" onClick={copyToken}>
                <Copy className="h-4 w-4" />
              </Button>
            </div>
            <p className="text-xs text-destructive font-medium">{t('tunnelTokenWarning')}</p>
          </div>
          <DialogFooter>
            <Button onClick={() => setNewToken(null)}>{t('confirm')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
});

TunnelAdminPanel.displayName = 'TunnelAdminPanel';

export default TunnelAdminPanel;
