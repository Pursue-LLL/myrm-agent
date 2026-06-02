'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconBot,
  IconSave,
  IconLoader,
  IconChat,
  IconPalette,
  IconCheck,
  IconDownload,
  IconRotateCcw,
} from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
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

/**
 * [INPUT]
 * AgentPreviewCardProps (POS: Agent settings editor state)
 *
 * [OUTPUT]
 * AgentPreviewCard: preview, avatar color picker, save/export/rollback/chat actions.
 *
 * [POS]
 * 智能体设置页预览卡片。只负责展示与触发父层动作，不直接读写配置持久化。
 */

// 预设头像颜色方案
export const avatarGradients = [
  { from: 'from-primary', to: 'to-violet-500', label: 'Purple' },
  { from: 'from-blue-500', to: 'to-cyan-500', label: 'Ocean' },
  { from: 'from-emerald-500', to: 'to-teal-500', label: 'Forest' },
  { from: 'from-orange-500', to: 'to-amber-500', label: 'Sunset' },
  { from: 'from-pink-500', to: 'to-rose-500', label: 'Rose' },
  { from: 'from-indigo-500', to: 'to-purple-500', label: 'Galaxy' },
];

interface AgentPreviewCardProps {
  name: string;
  description: string;
  selectedGradient: number;
  hasChanges: boolean;
  saving: boolean;
  exporting?: boolean;
  rollingBack?: boolean;
  snapshotCount?: number;
  skillCount: number;
  mcpCount: number;
  readonly?: boolean;
  onSave: () => void;
  onStartChat: () => void;
  onExport?: () => void;
  onRollback?: () => void;
  onOpenTimeMachine?: () => void;
  onGradientChange: (index: number) => void;
}

export function AgentPreviewCard({
  name,
  description,
  selectedGradient,
  hasChanges,
  saving,
  exporting = false,
  rollingBack = false,
  snapshotCount = 0,
  skillCount,
  mcpCount,
  readonly: isReadonly = false,
  onSave,
  onStartChat,
  onExport,
  onRollback,
  onOpenTimeMachine,
  onGradientChange,
}: AgentPreviewCardProps) {
  const t = useTranslations();
  const [rollbackConfirmOpen, setRollbackConfirmOpen] = useState(false);
  const currentGradient = avatarGradients[selectedGradient];

  return (
    <>
      <div className="space-y-6">
        <div className={cn('rounded-2xl overflow-hidden sticky top-24', 'bg-card border border-border/50')}>
          <div className="p-6 space-y-6">
            <div className="flex items-center justify-center">
              <div
                className={cn(
                  'relative w-32 h-32 rounded-3xl',
                  'bg-gradient-to-br',
                  currentGradient.from,
                  currentGradient.to,
                  'flex items-center justify-center',
                  'shadow-lg shadow-primary/20',
                  'transition-all duration-300',
                )}
              >
                <IconBot className="w-12 h-12 text-white" />
              </div>
            </div>

            <div className="text-center space-y-2">
              <h3 className="text-xl font-semibold text-foreground line-clamp-1">{name || t('agent.unnamed')}</h3>
              <p className="text-sm text-muted-foreground line-clamp-2">{description || t('agent.noDescription')}</p>
            </div>

            <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
              <div className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-muted/50">
                <span className="font-medium">{t('agent.skills')}</span>
                <span className="text-primary font-semibold">{skillCount}</span>
              </div>
              <div className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-muted/50">
                <span className="font-medium">{t('agent.mcp')}</span>
                <span className="text-primary font-semibold">{mcpCount}</span>
              </div>
            </div>

            {!isReadonly && (
              <div className="pt-4 border-t border-border/50">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <IconPalette className="w-4 h-4" />
                    {t('agent.avatarColor')}
                  </div>
                </div>
                <div className="grid grid-cols-6 gap-2">
                  {avatarGradients.map((gradient, index) => (
                    <button
                      key={index}
                      onClick={() => onGradientChange(index)}
                      className={cn(
                        'relative w-full aspect-square rounded-xl',
                        'bg-gradient-to-br',
                        gradient.from,
                        gradient.to,
                        'transition-all duration-200',
                        'hover:scale-110 hover:shadow-lg',
                        selectedGradient === index
                          ? 'ring-2 ring-primary ring-offset-2 ring-offset-background scale-110'
                          : 'hover:ring-2 hover:ring-primary/50',
                      )}
                      title={gradient.label}
                    >
                      {selectedGradient === index && (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <IconCheck className="w-4 h-4 text-white drop-shadow" />
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="p-4 bg-muted/30 space-y-3">
            {!isReadonly && (
              <Button
                disabled={!hasChanges || saving}
                onClick={onSave}
                variant="outline"
                className={cn(
                  'w-full gap-2 rounded-xl h-11',
                  hasChanges && 'bg-primary/10 border-primary/50 text-primary hover:bg-primary/20',
                )}
              >
                {saving ? <IconLoader className="w-4 h-4 animate-spin" /> : <IconSave className="w-4 h-4" />}
                {t('agent.save')}
              </Button>
            )}

            {onExport && (
              <Button
                disabled={saving || exporting || hasChanges}
                onClick={onExport}
                variant="outline"
                className="w-full gap-2 rounded-xl h-11"
                title={hasChanges ? t('agent.exportConfigSaveFirst') : t('agent.exportConfigTitle')}
              >
                {exporting ? <IconLoader className="w-4 h-4 animate-spin" /> : <IconDownload className="w-4 h-4" />}
                {t('agent.exportConfigAction')}
              </Button>
            )}

            {onRollback && (
              <div className="space-y-1.5">
                <Button
                  disabled={saving || rollingBack || snapshotCount === 0}
                  onClick={() => setRollbackConfirmOpen(true)}
                  variant="outline"
                  className="w-full gap-2 rounded-xl h-11 border-rose-500/20 hover:bg-rose-500/10 text-rose-500 hover:text-rose-600 transition-colors"
                  title={
                    snapshotCount === 0 ? t('agent.rollbackNoSnapshotTitle') : t('agent.rollbackLastAutoConfigTitle')
                  }
                >
                  {rollingBack ? (
                    <IconLoader className="w-4 h-4 animate-spin" />
                  ) : (
                    <IconRotateCcw className="w-4 h-4" />
                  )}
                  {t('agent.rollbackLastAutoConfig')}
                </Button>
                {snapshotCount > 1 && onOpenTimeMachine && (
                  <div className="flex justify-center">
                    <button
                      onClick={onOpenTimeMachine}
                      className="text-xs text-muted-foreground hover:text-primary transition-colors underline-offset-4 hover:underline"
                    >
                      {t('agent.viewAllSnapshots')}
                    </button>
                  </div>
                )}
              </div>
            )}

            <Button
              disabled={saving}
              onClick={onStartChat}
              className={cn(
                'group w-full gap-2 rounded-xl h-11',
                'bg-primary text-primary-foreground hover:bg-primary-hover',
                'shadow-[var(--shadow-brand)] hover:shadow-[var(--shadow-brand-lg)]',
              )}
            >
              <IconChat className="w-4 h-4 group-hover:rotate-12 transition-transform duration-300" />
              {t('agent.startChat')}
            </Button>
          </div>
        </div>
      </div>

      {onRollback ? (
        <AlertDialog open={rollbackConfirmOpen} onOpenChange={setRollbackConfirmOpen}>
          <AlertDialogContent className="max-w-md">
            <AlertDialogHeader>
              <AlertDialogTitle>{t('agent.rollbackConfirmTitle')}</AlertDialogTitle>
              <AlertDialogDescription>{t('agent.rollbackConfirmDescription')}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter className="flex-col-reverse sm:flex-row gap-2">
              <AlertDialogCancel disabled={rollingBack}>{t('agent.rollbackConfirmCancel')}</AlertDialogCancel>
              <AlertDialogAction
                disabled={rollingBack}
                onClick={() => {
                  setRollbackConfirmOpen(false);
                  onRollback();
                }}
                className="bg-rose-600 hover:bg-rose-700 text-white"
              >
                {rollingBack ? t('agent.rollbackConfirmRestoring') : t('agent.rollbackConfirmAction')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      ) : null}
    </>
  );
}
