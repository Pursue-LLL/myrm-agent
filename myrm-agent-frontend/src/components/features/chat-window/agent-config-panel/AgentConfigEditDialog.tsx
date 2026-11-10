'use client';

import { useCallback, useState } from 'react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { X } from 'lucide-react';
import { Dialog, DialogContent } from '@/components/primitives/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { Button } from '@/components/primitives/button';
import { ConfigEditor, type ConfigEditorProps, type SettingsSheetType } from './ConfigEditor';

const SkillsSection = dynamic(() => import('@/components/features/settings/sections/ai-tools/SkillsSection'), {
  ssr: false,
});
const MCPSection = dynamic(() => import('@/components/features/settings/sections/ai-tools/MCPSection'), { ssr: false });

export interface AgentConfigEditDialogProps extends ConfigEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * 每次打开计一次数，用作编辑器的 key：编辑器在打开那一刻按最新设置重建，
 * 即使关闭动画还没放完就再次打开，也不会带着上一次未保存的草稿。
 */
function useOpenSession(open: boolean): number {
  const [state, setState] = useState({ open, session: 0 });
  if (state.open !== open) {
    setState({ open, session: open ? state.session + 1 : state.session });
  }
  return state.session;
}

/**
 * 配置卡片的编辑弹窗。弹窗随面板常驻，表单只在打开期间存在（见 ConfigEditor）；
 * 技能与 MCP 的完整设置页在弹窗之上的侧边栏里打开。
 */
const AgentConfigEditDialog = ({ open, onOpenChange, ...editorProps }: AgentConfigEditDialogProps) => {
  const t = useTranslations('agent.configEditor');
  const session = useOpenSession(open);
  const [settingsSheetOpen, setSettingsSheetOpen] = useState(false);
  const [settingsSheetType, setSettingsSheetType] = useState<SettingsSheetType | null>(null);

  const openSettingsSheet = useCallback((type: SettingsSheetType) => {
    setSettingsSheetType(type);
    setSettingsSheetOpen(true);
  }, []);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg" data-testid="agent-config-edit-dialog">
          <ConfigEditor
            key={session}
            {...editorProps}
            onClose={() => onOpenChange(false)}
            onOpenSettingsSheet={openSettingsSheet}
          />
        </DialogContent>
      </Dialog>

      <Sheet open={settingsSheetOpen} onOpenChange={setSettingsSheetOpen}>
        <SheetContent
          side="right"
          hideCloseButton
          className="w-full sm:max-w-2xl lg:max-w-4xl p-0 overflow-y-auto"
          data-testid="agent-config-settings-sheet"
        >
          <SheetHeader className="sticky top-0 z-10 bg-background border-b border-border px-6 py-4">
            <div className="flex items-center justify-between">
              <SheetTitle>
                {settingsSheetType === 'skills'
                  ? t('skillsSection')
                  : settingsSheetType === 'mcp'
                    ? t('mcpSection')
                    : ''}
              </SheetTitle>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  setSettingsSheetOpen(false);
                  setSettingsSheetType(null);
                }}
                className="h-8 w-8"
              >
                <X size={18} />
              </Button>
            </div>
          </SheetHeader>
          <div className="p-6">
            {settingsSheetType === 'skills' ? <SkillsSection /> : settingsSheetType === 'mcp' ? <MCPSection /> : null}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
};

export default AgentConfigEditDialog;
