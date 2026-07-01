'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Building2, UserMinus, UserPlus, ArrowRightLeft, Shield, Clock } from 'lucide-react';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Badge } from '@/components/primitives/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import {
  type OrgInfo,
  type OrgMember,
  type HandoffLog,
  getMyOrg,
  listMembers,
  addMember,
  removeMember,
  offboardUser,
  transferVolume,
  listHandoffLogs,
} from '@/services/enterprise-org';

const ROLE_COLORS: Record<string, string> = {
  owner: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  admin: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  member: 'bg-gray-100 text-gray-700 dark:bg-gray-800/50 dark:text-gray-300',
};

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

const EnterpriseOrgSection = memo(() => {
  const t = useTranslations('settings.enterprise');
  const [org, setOrg] = useState<OrgInfo | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [logs, setLogs] = useState<HandoffLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showAddMember, setShowAddMember] = useState(false);
  const [showOffboard, setShowOffboard] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [newMemberEmail, setNewMemberEmail] = useState('');
  const [newMemberRole, setNewMemberRole] = useState('member');
  const [offboardUserId, setOffboardUserId] = useState('');
  const [transferSourceId, setTransferSourceId] = useState('');
  const [transferTargetId, setTransferTargetId] = useState('');

  const orgId = org?.id ?? '';

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const orgData = await getMyOrg();
      setOrg(orgData);
      const [membersData, logsData] = await Promise.all([
        listMembers(orgData.id),
        listHandoffLogs(orgData.id),
      ]);
      setMembers(membersData);
      setLogs(logsData);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load org data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAddMember = useCallback(async () => {
    if (!newMemberEmail.trim()) return;
    try {
      await addMember(orgId, newMemberEmail.trim(), newMemberRole);
      toast.success(t('memberAdded'));
      setShowAddMember(false);
      setNewMemberEmail('');
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to add member');
    }
  }, [orgId, newMemberEmail, newMemberRole, t, loadData]);

  const handleRemoveMember = useCallback(
    async (userId: string) => {
      try {
        await removeMember(orgId, userId);
        toast.success(t('memberRemoved'));
        await loadData();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Failed to remove member');
      }
    },
    [orgId, t, loadData]
  );

  const handleOffboard = useCallback(async () => {
    if (!offboardUserId.trim()) return;
    try {
      await offboardUser(orgId, offboardUserId.trim());
      toast.success(t('offboardSuccess'));
      setShowOffboard(false);
      setOffboardUserId('');
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Offboarding failed');
    }
  }, [orgId, offboardUserId, t, loadData]);

  const handleTransfer = useCallback(async () => {
    if (!transferSourceId.trim() || !transferTargetId.trim()) return;
    try {
      await transferVolume(orgId, transferSourceId.trim(), transferTargetId.trim());
      toast.success(t('transferSuccess'));
      setShowTransfer(false);
      setTransferSourceId('');
      setTransferTargetId('');
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Transfer failed');
    }
  }, [orgId, transferSourceId, transferTargetId, t, loadData]);

  if (loading) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-muted rounded w-1/3" />
          <div className="h-20 bg-muted rounded" />
        </div>
      </SettingsSection>
    );
  }

  if (error) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="text-center py-8 text-muted-foreground">
          <Building2 className="mx-auto mb-3 h-10 w-10 opacity-40" />
          <p className="text-sm">{t('notAvailable')}</p>
        </div>
      </SettingsSection>
    );
  }

  return (
    <div className="space-y-6">
      {/* Organization Info */}
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            {org?.name ?? t('title')}
          </span>
        }
        description={t('description')}
      >
        {org && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">{t('orgId')}:</span>{' '}
              <code className="text-xs bg-muted px-1 py-0.5 rounded">{org.id}</code>
            </div>
            {org.sso_domain && (
              <div>
                <span className="text-muted-foreground">{t('ssoDomain')}:</span> {org.sso_domain}
              </div>
            )}
            <div>
              <span className="text-muted-foreground">{t('retentionDays')}:</span>{' '}
              {org.archive_retention_days} {t('days')}
            </div>
          </div>
        )}
      </SettingsSection>

      {/* Members */}
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            {t('members')} ({members.length})
          </span>
        }
        action={
          <Button size="sm" variant="outline" onClick={() => setShowAddMember(true)}>
            <UserPlus className="h-4 w-4 mr-1" />
            {t('addMember')}
          </Button>
        }
      >
        <div className="space-y-2">
          {members.map((m) => (
            <div
              key={m.user_id}
              className="flex items-center justify-between py-2 px-3 rounded-lg bg-background/50 border border-border/30"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm">{m.user_id}</span>
                <Badge className={ROLE_COLORS[m.role] ?? ROLE_COLORS.member}>{m.role}</Badge>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{formatTimestamp(m.joined_at)}</span>
                {m.role !== 'owner' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={() => handleRemoveMember(m.user_id)}
                  >
                    <UserMinus className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </SettingsSection>

      {/* Offboarding Actions */}
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <ArrowRightLeft className="h-5 w-5" />
            {t('offboarding')}
          </span>
        }
        description={t('offboardingDesc')}
      >
        <div className="flex gap-3">
          <Button variant="outline" onClick={() => setShowOffboard(true)}>
            <UserMinus className="h-4 w-4 mr-1" />
            {t('offboardUser')}
          </Button>
          <Button variant="outline" onClick={() => setShowTransfer(true)}>
            <ArrowRightLeft className="h-4 w-4 mr-1" />
            {t('transferVolume')}
          </Button>
        </div>
      </SettingsSection>

      {/* Audit Logs */}
      {logs.length > 0 && (
        <SettingsSection
          title={
            <span className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              {t('auditLogs')}
            </span>
          }
        >
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {logs.map((log) => (
              <div
                key={log.id}
                className="flex items-center justify-between py-2 px-3 rounded-lg bg-background/50 border border-border/30 text-sm"
              >
                <div className="flex items-center gap-2">
                  <Badge variant={log.action === 'offboard' ? 'destructive' : 'default'}>{log.action}</Badge>
                  <span className="text-muted-foreground">
                    {log.source_user_id}
                    {log.target_user_id && ` → ${log.target_user_id}`}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={log.status === 'completed' ? 'default' : 'secondary'}>{log.status}</Badge>
                  <span className="text-xs text-muted-foreground">{formatTimestamp(log.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </SettingsSection>
      )}

      {/* Add Member Dialog */}
      <Dialog open={showAddMember} onOpenChange={setShowAddMember}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('addMember')}</DialogTitle>
            <DialogDescription>{t('addMemberDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>{t('userId')}</Label>
              <Input value={newMemberEmail} onChange={(e) => setNewMemberEmail(e.target.value)} placeholder="user_id" />
            </div>
            <div className="space-y-2">
              <Label>{t('role')}</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
                value={newMemberRole}
                onChange={(e) => setNewMemberRole(e.target.value)}
              >
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddMember(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={handleAddMember}>{t('confirm')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Offboard Dialog */}
      <Dialog open={showOffboard} onOpenChange={setShowOffboard}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('offboardUser')}</DialogTitle>
            <DialogDescription>{t('offboardUserDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>{t('userId')}</Label>
              <Input
                value={offboardUserId}
                onChange={(e) => setOffboardUserId(e.target.value)}
                placeholder="user_id"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowOffboard(false)}>
              {t('cancel')}
            </Button>
            <Button variant="destructive" onClick={handleOffboard}>
              {t('confirmOffboard')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Transfer Dialog */}
      <Dialog open={showTransfer} onOpenChange={setShowTransfer}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('transferVolume')}</DialogTitle>
            <DialogDescription>{t('transferVolumeDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>{t('sourceUserId')}</Label>
              <Input
                value={transferSourceId}
                onChange={(e) => setTransferSourceId(e.target.value)}
                placeholder="source_user_id"
              />
            </div>
            <div className="space-y-2">
              <Label>{t('targetUserId')}</Label>
              <Input
                value={transferTargetId}
                onChange={(e) => setTransferTargetId(e.target.value)}
                placeholder="target_user_id"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTransfer(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={handleTransfer}>{t('confirmTransfer')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
});

EnterpriseOrgSection.displayName = 'EnterpriseOrgSection';

export default EnterpriseOrgSection;
