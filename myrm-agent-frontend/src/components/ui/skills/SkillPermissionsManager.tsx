'use client';

/**
 * Skill Permissions Manager
 *
 * 管理已安装Skill的权限。显示每个Skill的required_permissions和granted_permissions，
 * 支持修改（授予/撤销）权限。
 *
 * 类似Android应用权限管理页面的设计。
 */

import { useTranslations } from 'next-intl';
import { useState, useEffect } from 'react';
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
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { toast } from '@/hooks/useToast';

export type SkillPermissionType =
  | 'file_read'
  | 'file_write'
  | 'file_delete'
  | 'shell_exec'
  | 'code_interpreter'
  | 'network_access'
  | 'env_var_access';

interface SkillPermissionInfo {
  permission: string;
  granted: boolean;
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

const PERMISSION_LABELS: Record<SkillPermissionType, string> = {
  file_read: '读取文件',
  file_write: '写入文件',
  file_delete: '删除文件',
  shell_exec: '执行Shell命令',
  code_interpreter: '执行代码',
  network_access: '网络访问',
  env_var_access: '环境变量访问',
};

const getPermissionLabel = (permission: SkillPermissionType): string => PERMISSION_LABELS[permission];

// 权限图标
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

// 判断是否危险
const isDangerousPermission = (permission: string): boolean => {
  return ['shell_exec', 'code_interpreter', 'file_delete'].includes(permission);
};

// 单个Skill的权限卡片
function SkillPermissionCard({
  skill,
  onPermissionChange,
}: {
  skill: SkillPermissionData;
  userId: string;
  onPermissionChange?: () => void;
}) {
  const t = useTranslations('skills.permissions');
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);

  const grantedSet = new Set(skill.grantedPermissions.map((p) => p.permission));

  const handleTogglePermission = async (permission: SkillPermissionType, grant: boolean) => {
    // Revoke权限时显示确认对话框
    if (!grant) {
      const confirmed = window.confirm(
        t('revokeConfirm', {
          defaultValue:
            '撤销权限后，Skill将无法执行相关操作。如果有正在运行的任务使用此权限，可能会被中断。\n\n是否继续？',
        }),
      );
      if (!confirmed) return;
    }

    setLoading(true);
    try {
      const endpoint = grant ? 'grant' : 'revoke';
      const response = await fetch(`/api/v1/skills/${skill.skillId}/permissions/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permissions: [permission] }),
      });

      if (!response.ok) throw new Error('Failed to update permission');

      toast({
        title: grant
          ? t('permissionGranted', { defaultValue: '权限已授予' })
          : t('permissionRevoked', { defaultValue: '权限已撤销' }),
        description: grant
          ? `${permission}`
          : t('revokeSuccess', {
              defaultValue: '权限已撤销。正在运行的任务可能会受到影响。',
            }),
      });

      onPermissionChange?.();
    } catch {
      toast({
        title: t('error', { defaultValue: '错误' }),
        description: t('updateFailed', { defaultValue: '更新权限失败' }),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const allPermissionsGranted = skill.requiredPermissions.every((p) => grantedSet.has(p));

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{skill.skillName}</h3>
            {allPermissionsGranted ? (
              <Badge variant="outline" className="border-green-500 text-green-500">
                <ShieldCheck className="mr-1 h-3 w-3" />
                {t('allGranted', { defaultValue: '已授权' })}
              </Badge>
            ) : (
              <Badge variant="outline" className="border-yellow-500 text-yellow-500">
                <AlertTriangle className="mr-1 h-3 w-3" />
                {t('partialGranted', { defaultValue: '部分授权' })}
              </Badge>
            )}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {skill.requiredPermissions.length} {t('permissionsRequired', { defaultValue: '项权限' })}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
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
                    <div className="text-sm font-medium">{getPermissionLabel(permission)}</div>
                    {isDangerous && (
                      <div className="text-xs text-destructive">
                        {t('dangerousPermission', { defaultValue: '危险权限，请谨慎授予' })}
                      </div>
                    )}
                  </div>
                </div>
                <Switch
                  checked={isGranted}
                  disabled={loading}
                  onCheckedChange={(checked) => handleTogglePermission(permission, checked)}
                />
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

// 主组件
export function SkillPermissionsManager({ userId, onPermissionChange }: SkillPermissionsManagerProps) {
  const t = useTranslations('skills.permissions');
  const [skills, setSkills] = useState<SkillPermissionData[]>([]);
  const [loading, setLoading] = useState(true);

  const loadSkillPermissions = async () => {
    setLoading(true);
    try {
      const skillsResponse = await fetch(`/api/v1/skills/available`);
      if (!skillsResponse.ok) throw new Error('Failed to load skills');

      const skillsData = await skillsResponse.json();
      const skillPermissions: SkillPermissionData[] = [];

      for (const skill of skillsData.skills || []) {
        if (skill.required_permissions && skill.required_permissions.length > 0) {
          try {
            const permsResponse = await fetch(`/api/v1/skills/${skill.id}/permissions`);
            if (permsResponse.ok) {
              const permsData = await permsResponse.json();
              skillPermissions.push({
                skillId: skill.id,
                skillName: skill.name,
                requiredPermissions: permsData.required_permissions || [],
                grantedPermissions: permsData.granted_permissions || [],
              });
            }
          } catch (error) {
            console.error(`Failed to load permissions for ${skill.id}:`, error);
          }
        }
      }

      setSkills(skillPermissions);
    } catch (error) {
      console.error('Failed to load skill permissions:', error);
      toast({
        title: t('error', { defaultValue: '错误' }),
        description: t('loadFailed', { defaultValue: '加载Skill权限失败' }),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userId) {
      loadSkillPermissions();
    }
  }, [userId]);

  const handlePermissionChange = () => {
    loadSkillPermissions();
    onPermissionChange?.();
  };

  const handleBulkRevoke = async (permissionType: SkillPermissionType) => {
    if (!userId) return;

    const confirmed = window.confirm(
      t('bulkRevoke.confirm', {
        defaultValue: `确定要撤销所有Skill的"${getPermissionLabel(permissionType)}"权限吗？这将影响多个Skill的运行。`,
      }),
    );

    if (!confirmed) return;

    try {
      const response = await fetch(`/api/v1/skills/permissions/bulk-revoke-by-type`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          permission_type: permissionType,
        }),
      });

      if (!response.ok) {
        throw new Error('Bulk revoke failed');
      }

      const result = await response.json();

      toast({
        title: t('bulkRevoke.success', { defaultValue: '批量撤销成功' }),
        description: t('bulkRevoke.affectedSkills', {
          defaultValue: `已撤销 ${result.total_revoked} 个权限，影响 ${result.affected_skills.length} 个Skill`,
        }),
      });

      // Reload permissions
      loadSkillPermissions();
      onPermissionChange?.();
    } catch (error) {
      console.error('Bulk revoke error:', error);
      toast({
        title: t('bulkRevoke.error', { defaultValue: '批量撤销失败' }),
        description: t('bulkRevoke.errorDescription', {
          defaultValue: '无法批量撤销权限，请重试',
        }),
        variant: 'destructive',
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="text-sm text-muted-foreground">{t('loading', { defaultValue: '加载中...' })}</div>
      </div>
    );
  }

  if (skills.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-12">
        <ShieldX className="h-8 w-8 text-muted-foreground" />
        <div className="text-sm text-muted-foreground">
          {t('noSkillsWithPermissions', { defaultValue: '没有需要权限的Skill' })}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">{t('title', { defaultValue: 'Skill权限管理' })}</h3>
          <p className="text-sm text-muted-foreground">
            {t('description', { defaultValue: '管理已安装Skill的权限，可以随时授予或撤销权限' })}
          </p>
        </div>
        <div className="flex gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <AlertTriangle className="mr-2 h-4 w-4" />
                {t('bulkRevoke.button', { defaultValue: '批量撤销' })}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => handleBulkRevoke('shell_exec')}>
                <Terminal className="mr-2 h-4 w-4" />
                {t('permissions.shell_exec', { defaultValue: '终端执行' })}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleBulkRevoke('file_write')}>
                <FileEdit className="mr-2 h-4 w-4" />
                {t('permissions.file_write', { defaultValue: '文件写入' })}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleBulkRevoke('file_delete')}>
                <Trash2 className="mr-2 h-4 w-4" />
                {t('permissions.file_delete', { defaultValue: '文件删除' })}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleBulkRevoke('network_access')}>
                <Globe className="mr-2 h-4 w-4" />
                {t('permissions.network_access', { defaultValue: '网络访问' })}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleBulkRevoke('code_interpreter')}>
                <Code className="mr-2 h-4 w-4" />
                {t('permissions.code_interpreter', { defaultValue: '代码执行' })}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleBulkRevoke('env_var_access')}>
                <Variable className="mr-2 h-4 w-4" />
                {t('permissions.env_var_access', { defaultValue: '环境变量' })}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleBulkRevoke('file_read')}>
                <FileText className="mr-2 h-4 w-4" />
                {t('permissions.file_read', { defaultValue: '文件读取' })}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" size="sm" onClick={loadSkillPermissions} disabled={loading}>
            {t('refresh', { defaultValue: '刷新' })}
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        {skills.map((skill) => (
          <SkillPermissionCard
            key={skill.skillId}
            skill={skill}
            userId={userId}
            onPermissionChange={handlePermissionChange}
          />
        ))}
      </div>
    </div>
  );
}

export default SkillPermissionsManager;
