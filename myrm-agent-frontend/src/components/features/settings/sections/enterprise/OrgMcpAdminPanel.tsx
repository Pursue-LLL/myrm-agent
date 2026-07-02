'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Plug, Plus, Trash2 } from 'lucide-react';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Badge } from '@/components/primitives/badge';
import { Switch } from '@/components/primitives/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import {
  type OrgMCPDelivery,
  type OrgMCPServer,
  createOrgMcpServer,
  deleteOrgMcpServer,
  listOrgMcpServers,
  updateOrgMcpServer,
} from '@/services/enterprise-org';

interface OrgMcpAdminPanelProps {
  orgId: string;
}

function showDeliveryToast(
  t: (key: string, values?: Record<string, string | number>) => string,
  delivery: OrgMCPDelivery,
) {
  const message = t('mcpDeliverySummary', {
    synced: delivery.synced,
    skipped: delivery.skipped,
    failed: delivery.failed,
  });
  if (delivery.failed > 0) {
    toast.error(message);
    return;
  }
  toast.success(message);
}

const OrgMcpAdminPanel = memo(({ orgId }: OrgMcpAdminPanelProps) => {
  const t = useTranslations('settings.enterprise');
  const [servers, setServers] = useState<OrgMCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<OrgMCPServer | null>(null);
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [type, setType] = useState<'sse' | 'streamable_http'>('sse');
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [authHeader, setAuthHeader] = useState('');

  const loadServers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listOrgMcpServers(orgId);
      setServers(data);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpLoadFailed'));
    } finally {
      setLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void loadServers();
  }, [loadServers]);

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !url.trim()) return;
    try {
      setSaving(true);
      const headers = authHeader.trim()
        ? { Authorization: authHeader.trim() }
        : undefined;
      const result = await createOrgMcpServer(orgId, {
        name: name.trim(),
        type,
        url: url.trim(),
        description: description.trim(),
        headers,
      });
      showDeliveryToast(t, result.delivery);
      setShowCreate(false);
      setName('');
      setUrl('');
      setDescription('');
      setAuthHeader('');
      await loadServers();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpCreateFailed'));
    } finally {
      setSaving(false);
    }
  }, [orgId, name, type, url, description, authHeader, t, loadServers]);

  const handleToggle = useCallback(
    async (server: OrgMCPServer) => {
      try {
        const result = await updateOrgMcpServer(orgId, server.id, {
          enabled: !server.enabled,
        });
        showDeliveryToast(t, result.delivery);
        await loadServers();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : t('mcpUpdateFailed'));
      }
    },
    [orgId, t, loadServers],
  );

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      const result = await deleteOrgMcpServer(orgId, deleteTarget.id);
      showDeliveryToast(t, result.delivery);
      setDeleteTarget(null);
      await loadServers();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpDeleteFailed'));
    }
  }, [orgId, deleteTarget, t, loadServers]);

  return (
    <SettingsSection
      title={
        <span className="flex items-center gap-2">
          <Plug className="h-5 w-5" />
          {t('mcpTitle')}
        </span>
      }
      description={t('mcpDescription')}
      action={
        <Button size="sm" variant="outline" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-1" />
          {t('mcpAdd')}
        </Button>
      }
    >
      {loading ? (
        <div className="animate-pulse space-y-2">
          <div className="h-14 bg-muted rounded-lg" />
          <div className="h-14 bg-muted rounded-lg" />
        </div>
      ) : servers.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4">{t('mcpEmpty')}</p>
      ) : (
        <div className="space-y-2">
          {servers.map((server) => (
            <div
              key={server.id}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-3 px-4 rounded-lg border border-border/40 bg-background/50"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-sm">{server.name}</span>
                  <Badge variant="secondary" className="text-xs uppercase">
                    {server.type.replace('_', ' ')}
                  </Badge>
                  {!server.enabled && (
                    <Badge variant="outline" className="text-xs">
                      {t('mcpDisabled')}
                    </Badge>
                  )}
                  {server.headers_configured && (
                    <Badge variant="outline" className="text-xs">
                      {t('mcpHeadersConfigured')}
                    </Badge>
                  )}
                </div>
                {server.url && (
                  <p className="text-xs text-muted-foreground truncate">{server.url}</p>
                )}
                {server.description && (
                  <p className="text-xs text-muted-foreground">{server.description}</p>
                )}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <div className="flex items-center gap-2">
                  <Label htmlFor={`mcp-enabled-${server.id}`} className="text-xs text-muted-foreground">
                    {t('mcpEnabled')}
                  </Label>
                  <Switch
                    id={`mcp-enabled-${server.id}`}
                    checked={server.enabled}
                    onCheckedChange={() => void handleToggle(server)}
                  />
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setDeleteTarget(server)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('mcpAdd')}</DialogTitle>
            <DialogDescription>{t('mcpAddDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>{t('mcpName')}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="company-crm" />
            </div>
            <div className="space-y-2">
              <Label>{t('mcpType')}</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
                value={type}
                onChange={(e) => setType(e.target.value as 'sse' | 'streamable_http')}
              >
                <option value="sse">SSE</option>
                <option value="streamable_http">Streamable HTTP</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label>{t('mcpUrl')}</Label>
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://mcp.example.com/sse"
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
            <div className="space-y-2">
              <Label>{t('mcpAuthHeader')}</Label>
              <Input
                value={authHeader}
                onChange={(e) => setAuthHeader(e.target.value)}
                placeholder={t('mcpAuthHeaderPlaceholder')}
                type="password"
                autoComplete="off"
              />
            </div>
            <p className="text-xs text-muted-foreground">{t('mcpSleepingHint')}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={() => void handleCreate()} disabled={saving || !name.trim() || !url.trim()}>
              {t('confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('mcpDeleteTitle')}</DialogTitle>
            <DialogDescription>
              {t('mcpDeleteDesc', { name: deleteTarget?.name ?? '' })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              {t('cancel')}
            </Button>
            <Button variant="destructive" onClick={() => void handleDelete()}>
              {t('confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsSection>
  );
});

OrgMcpAdminPanel.displayName = 'OrgMcpAdminPanel';

export default OrgMcpAdminPanel;
