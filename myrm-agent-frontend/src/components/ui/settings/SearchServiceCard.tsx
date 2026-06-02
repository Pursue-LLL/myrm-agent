'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconCheck,
  IconLoader,
  IconPencil,
  IconTrash,
  IconZap,
  IconAlertCircle,
} from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { SearchServiceConfigItem, SearchServiceConfig, ValidationResult } from '@/store/config/types';
import { getSearchServiceDisplayName } from '@/store/config/searchService';
import { isSoftSearchServiceValidationFailure } from '@/services/llm-config';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface SearchServiceCardProps {
  config: SearchServiceConfigItem;
  conflictingService?: SearchServiceConfigItem;
  onEdit: () => void;
  onDelete: () => void;
  onEnable: (latency?: number) => void;
  onValidate: (config: SearchServiceConfig) => Promise<ValidationResult>;
}

const SearchServiceCard = memo(
  ({ config, conflictingService, onEdit, onDelete, onEnable, onValidate }: SearchServiceCardProps) => {
    const t = useTranslations('settings');
    const [isValidating, setIsValidating] = useState(false);
    const [validationError, setValidationError] = useState<string | null>(null);
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [confirmEnableOpen, setConfirmEnableOpen] = useState(false);

    // 处理启用按钮点击
    const handleEnableClick = async () => {
      if (config.enabled) return;

      if (conflictingService) {
        setConfirmEnableOpen(true);
        return;
      }

      await performEnable();
    };

    // 执行实际的启用操作
    const performEnable = async () => {
      setIsValidating(true);
      setValidationError(null);

      try {
        const result = await onValidate({
          search_service: config.search_service,
          api_key: config.api_key,
          api_base: config.api_base,
          extra_params: config.extra_params,
        });

        if (result.success) {
          onEnable(result.latency);
        } else {
          const warningMessage = result.message || t('searchServiceValidationFailed');
          setValidationError(warningMessage);
          // 外部搜索服务的验证失败如果只是配额/限流/瞬时网络问题，仍允许启用配置。
          if (config.search_service === 'searxng' || isSoftSearchServiceValidationFailure(result)) {
            onEnable(result.latency || 0);
          }
        }
      } catch (error) {
        setValidationError(error instanceof Error ? error.message : String(error));
      } finally {
        setIsValidating(false);
      }
    };

    // 确认启用（有冲突时）
    const handleConfirmEnable = async () => {
      setConfirmEnableOpen(false);
      await performEnable();
    };

    const handleDeleteConfirm = async () => {
      onDelete();
    };

    return (
      <div
        className={cn(
          'relative group rounded-xl border p-4 transition-all duration-200',
          config.enabled ? 'border-primary/50 bg-primary/5' : 'border-border bg-card hover:border-border/80',
        )}
      >
        {/* 启用状态标识 */}
        {config.enabled && (
          <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-primary flex items-center justify-center shadow-md">
            <IconCheck className="w-3.5 h-3.5 text-white" />
          </div>
        )}

        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            {/* 配置名称或服务类型名称 */}
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-medium text-foreground truncate">
                {config.name || getSearchServiceDisplayName(config.search_service)}
              </h3>
              {/* 角色标签 */}
              <span
                className={cn(
                  'shrink-0 px-2 py-0.5 text-xs rounded-full font-medium',
                  config.role === 'primary'
                    ? 'bg-primary/10 dark:bg-primary/20 text-primary'
                    : 'bg-[rgb(245,174,116)]/20 dark:bg-[rgb(232,140,48)]/25 text-[rgb(217,112,56)] dark:text-[rgb(232,140,48)]',
                )}
              >
                {config.role === 'primary' ? t('primaryService') : t('fallbackService')}
              </span>
              {/* 如果有自定义名称，显示服务商标签 */}
              {config.name && (
                <span className="shrink-0 px-2 py-0.5 text-xs rounded-full bg-secondary text-muted-foreground">
                  {getSearchServiceDisplayName(config.search_service)}
                </span>
              )}
            </div>

            {/* 延迟信息 */}
            {config.latency && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <IconZap className="w-3 h-3 text-amber-500" />
                <span>{config.latency}ms</span>
              </div>
            )}

            {/* 验证错误 */}
            {validationError && (
              <div className="mt-2 flex items-start gap-1.5 text-xs text-red-500">
                <IconAlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
                <span>{validationError}</span>
              </div>
            )}
          </div>

          {/* 操作按钮 */}
          <div className="flex items-center gap-2">
            {/* 启用/验证按钮 */}
            {!config.enabled && (
              <button
                onClick={handleEnableClick}
                disabled={isValidating}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors',
                  isValidating
                    ? 'bg-secondary text-muted-foreground cursor-wait'
                    : 'bg-primary text-white hover:bg-primary/90',
                )}
              >
                {isValidating ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : t('searchService.enable')}
              </button>
            )}

            {config.enabled && (
              <span className="px-3 py-1.5 text-sm font-medium text-primary bg-primary/10 rounded-lg">
                {t('searchService.enabled')}
              </span>
            )}

            {/* 编辑按钮 */}
            <button
              onClick={onEdit}
              className="p-2 text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg transition-colors"
              title={t('common.edit')}
            >
              <IconPencil className="w-4 h-4" />
            </button>

            {/* 删除按钮 */}
            <ConfirmDialog
              trigger={
                <button
                  className="p-2 text-muted-foreground hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all duration-200 hover:scale-110 active:scale-95"
                  title={t('common.delete')}
                >
                  <IconTrash className="w-4 h-4 transition-transform duration-200 hover:rotate-12" />
                </button>
              }
              open={deleteDialogOpen}
              onOpenChange={setDeleteDialogOpen}
              title={t('searchService.deleteTitle')}
              description={t('searchService.deleteDescription')}
              confirmText={t('common.delete')}
              cancelText={t('common.cancel')}
              variant="destructive"
              onConfirm={handleDeleteConfirm}
            />
          </div>
        </div>

        {/* 启用确认对话框（有冲突时） */}
        <AlertDialog open={confirmEnableOpen} onOpenChange={setConfirmEnableOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('searchService.enableConflictTitle')}</AlertDialogTitle>
              <AlertDialogDescription>
                {conflictingService
                  ? t('searchService.enableConflictDescription', {
                      currentName:
                        conflictingService.name || getSearchServiceDisplayName(conflictingService.search_service),
                      newName: config.name || getSearchServiceDisplayName(config.search_service),
                      role: config.role === 'primary' ? t('primaryService') : t('fallbackService'),
                    })
                  : ''}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={handleConfirmEnable}>{t('common.confirm')}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  },
);

SearchServiceCard.displayName = 'SearchServiceCard';

export default SearchServiceCard;
