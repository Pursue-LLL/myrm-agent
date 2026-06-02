'use client';

/**
 * Skill Permission Approval Dialog
 *
 * 当用户安装/启用Skill时，显示Skill声明的required_permissions，
 * 用户批准后才能继续。支持"Always Allow"功能。
 *
 * 借鉴Manus Skills Marketplace的权限审批设计。
 */

import { useTranslations } from 'next-intl';
import { useState } from 'react';
import {
  Shield,
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertTriangle,
  FileEdit,
  Terminal,
  Code,
  Globe,
  Variable,
  Trash2,
  FileText,
} from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

// 权限类型
export type SkillPermissionType =
  | 'file_read'
  | 'file_write'
  | 'file_delete'
  | 'shell_exec'
  | 'code_interpreter'
  | 'network_access'
  | 'env_var_access';

// 权限模板类型
export type PermissionTemplateType =
  | 'developer_tools'
  | 'data_analysis'
  | 'web_automation'
  | 'system_admin'
  | 'readonly';

export interface SkillPermissionRequest {
  skillId: string;
  skillName: string;
  description: string;
  requiredPermissions: SkillPermissionType[];
  allowedDomains?: string[] | null;
}

interface SkillPermissionApprovalDialogProps {
  open: boolean;
  request: SkillPermissionRequest | null;
  onOpenChange: (open: boolean) => void;
  onApprove: (alwaysAllow: boolean, template?: PermissionTemplateType) => void;
  onDeny: () => void;
  isLoading?: boolean;
}

// 权限图标映射
const getPermissionIcon = (permission: SkillPermissionType) => {
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

// 判断权限是否危险
const isDangerousPermission = (permission: SkillPermissionType): boolean => {
  return ['shell_exec', 'code_interpreter', 'file_delete'].includes(permission);
};

export function SkillPermissionApprovalDialog({
  open,
  request,
  onOpenChange,
  onApprove,
  onDeny,
  isLoading,
}: SkillPermissionApprovalDialogProps) {
  const t = useTranslations('skills.permissions');
  const [alwaysAllow, setAlwaysAllow] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<PermissionTemplateType | ''>('');

  if (!request) return null;

  const hasDangerousPermissions = request.requiredPermissions.some(isDangerousPermission);
  const dangerousPermissions = request.requiredPermissions.filter(isDangerousPermission);
  const safePermissions = request.requiredPermissions.filter((permission) => !isDangerousPermission(permission));

  // 处理模板选择
  const handleTemplateSelect = (template: PermissionTemplateType | '') => {
    setSelectedTemplate(template);
    // 模板选择逻辑将在后端API调用时处理，前端仅更新UI状态
    // 实际权限授予由onApprove处理
  };

  const handleApprove = () => {
    onApprove(alwaysAllow, selectedTemplate || undefined);
    setAlwaysAllow(false);
    setSelectedTemplate('');
  };

  const handleDeny = () => {
    onDeny();
    setAlwaysAllow(false);
  };

  // 权限标签映射
  const permissionLabels: Record<SkillPermissionType, { label: string; description: string }> = {
    file_read: {
      label: t('types.fileRead.label', { defaultValue: '读取文件' }),
      description: t('types.fileRead.description', { defaultValue: '从工作区读取文件内容' }),
    },
    file_write: {
      label: t('types.fileWrite.label', { defaultValue: '写入文件' }),
      description: t('types.fileWrite.description', { defaultValue: '在工作区创建或修改文件' }),
    },
    file_delete: {
      label: t('types.fileDelete.label', { defaultValue: '删除文件' }),
      description: t('types.fileDelete.description', { defaultValue: '从工作区删除文件' }),
    },
    shell_exec: {
      label: t('types.shellExec.label', { defaultValue: '执行Shell命令' }),
      description: t('types.shellExec.description', { defaultValue: '在系统中执行shell命令' }),
    },
    code_interpreter: {
      label: t('types.codeInterpreter.label', { defaultValue: '执行代码' }),
      description: t('types.codeInterpreter.description', {
        defaultValue: '执行Python、Node.js等代码',
      }),
    },
    network_access: {
      label: t('types.networkAccess.label', { defaultValue: '网络访问' }),
      description: t('types.networkAccess.description', { defaultValue: '发起HTTP/HTTPS请求' }),
    },
    env_var_access: {
      label: t('types.envVarAccess.label', { defaultValue: '环境变量访问' }),
      description: t('types.envVarAccess.description', { defaultValue: '读取或修改环境变量' }),
    },
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[550px]">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-full',
                hasDangerousPermissions ? 'bg-destructive/10 text-destructive' : 'bg-primary/10 text-primary',
              )}
            >
              {hasDangerousPermissions ? <ShieldAlert className="h-5 w-5" /> : <Shield className="h-5 w-5" />}
            </div>
            <div>
              <DialogTitle>{t('approvalTitle', { defaultValue: 'Skill 权限审批' })}</DialogTitle>
              <DialogDescription className="mt-1">
                {t('approvalDescription', {
                  defaultValue: '此Skill需要以下权限才能正常工作',
                })}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Skill 信息 */}
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              {t('skillName', { defaultValue: 'Skill名称' })}
            </label>
            <div className="mt-1 text-sm font-semibold">{request.skillName}</div>
            {request.description && <div className="mt-1 text-sm text-muted-foreground">{request.description}</div>}
          </div>

          {/* 权限模板选择器 */}
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              {t('template.label', { defaultValue: '使用权限模板' })}
            </label>
            <Select value={selectedTemplate} onValueChange={handleTemplateSelect}>
              <SelectTrigger className="mt-2">
                <SelectValue placeholder={t('template.placeholder', { defaultValue: '选择标准模板快速授权' })} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">{t('template.none', { defaultValue: '不使用模板' })}</SelectItem>
                <SelectItem value="readonly">
                  {t('template.readonly', { defaultValue: '只读模式' })} (file_read)
                </SelectItem>
                <SelectItem value="data_analysis">
                  {t('template.dataAnalysis', { defaultValue: '数据分析' })} (file_read, code_interpreter)
                </SelectItem>
                <SelectItem value="web_automation">
                  {t('template.webAutomation', { defaultValue: '网络自动化' })} (network_access, file_write)
                </SelectItem>
                <SelectItem value="developer_tools">
                  {t('template.developerTools', { defaultValue: '开发工具' })} (file_read, file_write, shell_exec)
                </SelectItem>
                <SelectItem value="system_admin">
                  {t('template.systemAdmin', { defaultValue: '系统管理员（危险）' })} (ALL)
                </SelectItem>
              </SelectContent>
            </Select>
            {selectedTemplate && (
              <p className="mt-2 text-xs text-muted-foreground">
                {t('template.hint', {
                  defaultValue: '模板将自动勾选对应权限',
                })}
              </p>
            )}
          </div>

          {/* 权限列表（分组显示） */}
          <div className="space-y-4">
            {/* 危险权限组 */}
            {dangerousPermissions.length > 0 && (
              <div>
                <label className="text-sm font-medium text-destructive flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  {t('dangerousPermissions', { defaultValue: '危险权限' })}
                </label>
                <div className="mt-2 space-y-2">
                  {dangerousPermissions.map((permission) => {
                    const Icon = getPermissionIcon(permission);
                    const info = permissionLabels[permission];

                    return (
                      <div
                        key={permission}
                        className="flex items-start gap-3 rounded-lg border border-destructive/50 bg-destructive/5 p-3"
                      >
                        <Icon className="mt-0.5 h-4 w-4 text-destructive" />
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{info.label}</span>
                            <Badge variant="destructive" className="h-5 text-xs">
                              {t('dangerous', { defaultValue: '危险' })}
                            </Badge>
                          </div>
                          <div className="mt-0.5 text-xs text-muted-foreground">{info.description}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 普通权限组 */}
            {safePermissions.length > 0 && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  {t('normalPermissions', { defaultValue: '普通权限' })}
                </label>
                <div className="mt-2 space-y-2">
                  {safePermissions.map((permission) => {
                    const Icon = getPermissionIcon(permission);
                    const info = permissionLabels[permission];

                    return (
                      <div
                        key={permission}
                        className="flex items-start gap-3 rounded-lg border border-border bg-muted/50 p-3"
                      >
                        <Icon className="mt-0.5 h-4 w-4 text-muted-foreground" />
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{info.label}</span>
                          </div>
                          <div className="mt-0.5 text-xs text-muted-foreground">{info.description}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 网络访问权限 (DLP) */}
            {request.allowedDomains && request.allowedDomains.length > 0 && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  {t('networkAccess', { defaultValue: '网络访问白名单' })}
                </label>
                <div className="mt-2 space-y-2">
                  <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/50 p-3">
                    <Globe className="mt-0.5 h-4 w-4 text-muted-foreground" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">
                          {t('allowedDomains', { defaultValue: '允许访问的域名' })}
                        </span>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {request.allowedDomains.map((domain) => (
                          <Badge key={domain} variant="secondary" className="text-xs font-mono">
                            {domain}
                          </Badge>
                        ))}
                      </div>
                      <div className="mt-1.5 text-xs text-muted-foreground">
                        {t('allowedDomainsDesc', {
                          defaultValue: '此 Skill 仅被允许向以上域名发起网络请求，防止数据外泄。',
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 危险权限警告 */}
          {hasDangerousPermissions && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="text-sm">
                {t('dangerousWarning', {
                  defaultValue: '此Skill请求了危险权限，请确认Skill来源可信后再批准。',
                })}
              </AlertDescription>
            </Alert>
          )}

          {/* Always Allow 选项 */}
          {!hasDangerousPermissions && (
            <div className="flex items-center space-x-2">
              <Checkbox
                id="always-allow-skill"
                checked={alwaysAllow}
                onCheckedChange={(checked) => setAlwaysAllow(checked === true)}
              />
              <label htmlFor="always-allow-skill" className="cursor-pointer text-sm text-muted-foreground">
                {t('alwaysAllow', { defaultValue: '始终允许此Skill的权限请求' })}
              </label>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={handleDeny} disabled={isLoading}>
            <XCircle className="mr-2 h-4 w-4" />
            {t('deny', { defaultValue: '拒绝' })}
          </Button>
          <Button
            variant={hasDangerousPermissions ? 'destructive' : 'default'}
            onClick={handleApprove}
            disabled={isLoading}
          >
            <CheckCircle className="mr-2 h-4 w-4" />
            {hasDangerousPermissions
              ? t('approveAnyway', { defaultValue: '仍然批准' })
              : t('approve', { defaultValue: '批准' })}
          </Button>
          {!hasDangerousPermissions && (
            <Button
              variant="default"
              onClick={() => {
                setAlwaysAllow(true);
                handleApprove();
              }}
              disabled={isLoading}
              className="bg-green-600 hover:bg-green-700"
            >
              <CheckCircle className="mr-2 h-4 w-4" />
              {t('allowAll', { defaultValue: '全部允许' })}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SkillPermissionApprovalDialog;
