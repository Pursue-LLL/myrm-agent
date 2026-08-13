'use client';

/**
 * Skill Permissions Manager
 *
 * 管理已安装 Skill 的权限：展示每个 Skill 的 required/granted 权限，
 * 支持单权限授予/撤销，以及按权限类型一键批量撤销（安全应急场景）。
 * 入口：设置 → AI 工具 → 技能 → 「权限管理」Tab。
 */

import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';
import {
  Shield,
  ShieldCheck,
  ShieldX,
  AlertTriangle,
  FileEdit,
  Terminal,
  Code,
  Globe,
  Variable,
  Trash2,
  FileText,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Card } from '@/components/primitives/card';
import { Switch } from '@/components/primitives/switch';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { toast } from '@/hooks/shared/useToast';

export type SkillPermissionType =
  'file_read' | 'file_write' | 'file_delete' | 'shell_exec' | 'code_interpreter' | 'network_access' | 'env_var_access';

const KNOWN_PERMISSION_TYPES: SkillPermissionType[] = [
  'shell_exec',
  'file_write',
  'file_delete',
  'network_access',
  'code_interpreter',
  'env_var_access',
  'file_read',
];

interface SkillPermissionInfo {
  permission: string;
  grantedAt?: string;
}

interface SkillPermissionData {
  skillId: string;
  skillName: string;
  requiredPermissions: SkillPermissionType[];
  grantedPermissions: SkillPermissionInfo[];
}

interface SkillPermissionsManagerProps {
  userId: string;
  onPermissionChange?: () => void;
}

const toCamelCase = (value: string): string => value.replace(/_([a-z])/g, (_, char: string) => char.toUpperCase());

const getPermissionIcon = (permission: string) => {
  switch (permission) {
    case 'file_read':
      return FileText;
    case 'file_write':
      return FileEdit;
    case 'file_delete':
      return Trash2;
    case 'shell_exec':
      return Terminal;
    case 'code_interpreter':
      return Code;
    case 'network_access':
      return Globe;
    case 'env_var_access':
      return Variable;
    default:
      return Shield;
  }
};

const isDangerousPermission = (permission: string): boolean =>
  ['shell_exec', 'code_interpreter', 'file_delete'].includes(permission);

interface SkillPermissionCardProps {
  skill: SkillPermissionData;
  disabled: boolean;
  onTogglePermission: (skill: SkillPermissionData, permission: SkillPermissionType, grant: boolean) => void;
}

function SkillPermissionCard({ skill, disabled, onTogglePermission }: SkillPermissionCardProps) {
  const t = useTranslations('skills.permissions');
  const [expanded, setExpanded] = useState(false);

  const grantedSet = new Set(skill.grantedPermissions.map((p) => p.permission));
  const allPermissionsGranted = skill.requiredPermissions.every((p) => grantedSet.has(p));
  const permissionLabel = (permission: SkillPermissionType): string =>
    t(`types.${toCamelCase(permission)}.label` as Parameters<typeof t>[0]);

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{skill.skillName}</h3>
            {allPermissionsGranted ? (
              <Badge variant="outline" className="border-green-500 text-green-500">
                <ShieldCheck className="mr-1 h-3 w-3" />
                {t('allGranted')}
              </Badge>
            ) : (
              <Badge variant="outline" className="border-yellow-500 text-yellow-500">
                <AlertTriangle className="mr-1 h-3 w-3" />
                {t('partialGranted')}
              </Badge>
            )}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {skill.requiredPermissions.length} {t('permissionsRequired')}
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? t('collapse') : t('expand')}
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
      </div>

      {expanded && (
        <div className="mt-4 space-y-2 border-t pt-4">
          {skill.requiredPermissions.map((permission) => {
            const Icon = getPermissionIcon(permission);
            const isDangerous = isDangerousPermission(permission);
            const isGranted = grantedSet.has(permission);

            return (
              <div
                key={permission}
                className={cn(
                  'flex items-center justify-between rounded-full border p-3',
                  isDangerous && !isGranted && 'border-destructive/50 bg-destructive/5',
                )}
              >
                <div className="flex items-center gap-3">
                  <Icon className={cn('h-4 w-4', isDangerous ? 'text-destructive' : 'text-muted-foreground')} />
                  <div>
                    <div className="text-sm font-medium">{permissionLabel(permission)}</div>
                    {isDangerous && <div className="text-xs text-destructive">{t('dangerousPermission')}</div>}
                  </div>
                </div>
                <Switch
                  checked={isGranted}
                  disabled={disabled}
                  onCheckedChange={(checked) => onTogglePermission(skill, permission, checked)}
                />
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

export function SkillPermissionsManager({ userId, onPermissionChange }: SkillPermissionsManagerProps) {
  const t = useTranslations('skills.permissions');
  const [skills, setSkills] = useState<SkillPermissionData[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingRevoke, setPendingRevoke] = useState<{
    skill: SkillPermissionData;
    permission: SkillPermissionType;
  } | null>(null);
  const [pendingBulkRevoke, setPendingBulkRevoke] = useState<SkillPermissionType | null>(null);

  const loadSkillPermissions = useCallback(async () => {
    setLoading(true);
    try {
      const skillsResponse = await fetch(`/api/v1/skills/available`);
      if (!skillsResponse.ok) {throw new Error('Failed to load skills');}

      const skillsData = (await skillsResponse.json()) as { skills?: { id: string; name: string }[] };
      const allSkills = skillsData.skills || [];

      // 并发拉取每个技能的权限声明，仅保留声明了 required_permissions 的技能
      const entries = await Promise.all(
        allSkills.map(async (skill) => {
          try {
            const permsResponse = await fetch(`/api/v1/skills/${skill.id}/permissions`);
            if (!permsResponse.ok) {return null;}
            const permsData = (await permsResponse.json()) as {
              required_permissions?: string[];
              granted_permissions?: SkillPermissionInfo[];
            };
            const requiredPermissions = (permsData.required_permissions || []).filter((p) =>
              (KNOWN_PERMISSION_TYPES as string[]).includes(p),
            ) as SkillPermissionType[];
            if (requiredPermissions.length === 0) {return null;}
            return {
              skillId: skill.id,
              skillName: skill.name,
              requiredPermissions,
              grantedPermissions: permsData.granted_permissions || [],
            };
          } catch (error) {
            console.error(`Failed to load permissions for ${skill.id}:`, error);
            return null;
          }
        }),
      );

      setSkills(entries.filter((e): e is SkillPermissionData => e !== null));
    } catch (error) {
      console.error('Failed to load skill permissions:', error);
      toast({
        title: t('error'),
        description: t('loadFailed'),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (userId) {
      void loadSkillPermissions();
    }
  }, [userId, loadSkillPermissions]);

  const updatePermission = useCallback(
    async (skill: SkillPermissionData, permission: SkillPermissionType, grant: boolean) => {
      const endpoint = grant ? 'grant' : 'revoke';
      try {
        const response = await fetch(`/api/v1/skills/${skill.skillId}/permissions/${endpoint}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ permissions: [permission] }),
        });
        if (!response.ok) {throw new Error('Failed to update permission');}

        setSkills((prev) =>
          prev.map((s) =>
            s.skillId === skill.skillId
              ? {
                  ...s,
                  grantedPermissions: grant
                    ? [...s.grantedPermissions, { permission }]
                    : s.grantedPermissions.filter((g) => g.permission !== permission),
                }
              : s,
          ),
        );

        toast({
          title: grant ? t('permissionGranted') : t('permissionRevoked'),
          description: grant ? permission : t('revokeSuccess'),
        });

        onPermissionChange?.();
      } catch (error) {
        console.error('Failed to update permission:', error);
        toast({
          title: t('error'),
          description: t('updateFailed'),
          variant: 'destructive',
        });
      }
    },
    [onPermissionChange, t],
  );

  const handleTogglePermission = (skill: SkillPermissionData, permission: SkillPermissionType, grant: boolean) => {
    if (grant) {
      void updatePermission(skill, permission, true);
    } else {
      setPendingRevoke({ skill, permission });
    }
  };

  const confirmRevoke = async () => {
    if (!pendingRevoke) {return;}
    const { skill, permission } = pendingRevoke;
    setPendingRevoke(null);
    await updatePermission(skill, permission, false);
  };

  const bulkRevoke = async (permissionType: SkillPermissionType) => {
    try {
      const response = await fetch(`/api/v1/skills/permissions/bulk-revoke-by-type`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permission_type: permissionType }),
      });
      if (!response.ok) {throw new Error('Bulk revoke failed');}

      const result = (await response.json()) as {
        total_revoked?: number;
        affected_skills?: string[];
      };
      toast({
        title: t('bulkRevoke.success'),
        description: t('bulkRevoke.affectedSkills', {
          count: String(result.total_revoked ?? 0),
          skills: String((result.affected_skills || []).length),
        }),
      });

      setSkills((prev) =>
        prev.map((s) => ({
          ...s,
          grantedPermissions: s.grantedPermissions.filter((g) => g.permission !== permissionType),
        })),
      );
      onPermissionChange?.();
    } catch (error) {
      console.error('Bulk revoke error:', error);
      toast({
        title: t('bulkRevoke.error'),
        description: t('bulkRevoke.errorDescription'),
        variant: 'destructive',
      });
    }
  };

  const permissionLabel = (permission: SkillPermissionType): string =>
    t(`types.${toCamelCase(permission)}.label` as Parameters<typeof t>[0]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="text-sm text-muted-foreground">{t('loading')}</div>
      </div>
    );
  }

  if (skills.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-12">
        <ShieldX className="h-8 w-8 text-muted-foreground" />
        <div className="text-sm text-muted-foreground">{t('noSkillsWithPermissions')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold">{t('title')}</h3>
          <p className="text-sm text-muted-foreground">{t('description')}</p>
        </div>
        <div className="flex gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <AlertTriangle className="mr-2 h-4 w-4" />
                {t('bulkRevoke.button')}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {KNOWN_PERMISSION_TYPES.map((permission) => {
                const Icon = getPermissionIcon(permission);
                return (
                  <DropdownMenuItem key={permission} onClick={() => setPendingBulkRevoke(permission)}>
                    <Icon className="mr-2 h-4 w-4" />
                    {permissionLabel(permission)}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" size="sm" onClick={() => void loadSkillPermissions()} disabled={loading}>
            {t('refresh')}
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        {skills.map((skill) => (
          <SkillPermissionCard
            key={skill.skillId}
            skill={skill}
            disabled={loading}
            onTogglePermission={handleTogglePermission}
          />
        ))}
      </div>

      <AlertDialog open={!!pendingRevoke} onOpenChange={(open) => !open && setPendingRevoke(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('revokeTitle', {
                permission: pendingRevoke ? permissionLabel(pendingRevoke.permission) : '',
                skill: pendingRevoke?.skill.skillName ?? '',
              })}
            </AlertDialogTitle>
            <AlertDialogDescription>{t('revokeConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => void confirmRevoke()}
            >
              {t('confirmRevoke')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!pendingBulkRevoke} onOpenChange={(open) => !open && setPendingBulkRevoke(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('bulkRevoke.confirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('bulkRevoke.confirm', {
                permission: pendingBulkRevoke ? permissionLabel(pendingBulkRevoke) : '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (pendingBulkRevoke) {
                  void bulkRevoke(pendingBulkRevoke);
                }
              }}
            >
              {t('confirmRevoke')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default SkillPermissionsManager;
