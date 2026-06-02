/**
 * 命令编辑器对话框
 *
 * 创建或编辑快捷指令
 */

'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useCommandStore } from '@/store/useCommandStore';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/lib/utils/toast';
import type { SlashCommand } from '@/types/command';

interface CommandEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  command?: SlashCommand | null;
}

export const CommandEditor: React.FC<CommandEditorProps> = ({ open, onOpenChange, command }) => {
  const t = useTranslations('settings.commands.editor');
  const { addCommand, updateCommand } = useCommandStore();

  const [name, setName] = useState('');
  const [template, setTemplate] = useState('');

  // 编辑模式：填充现有命令数据
  useEffect(() => {
    if (command) {
      setName(command.name);
      setTemplate(command.template);
    } else {
      // 新建模式：清空表单
      setName('');
      setTemplate('');
    }
  }, [command, open]);

  // 验证表单
  const validate = (): boolean => {
    if (!name.trim()) {
      toast.error(t('validation.nameRequired'));
      return false;
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
      toast.error(t('validation.nameInvalid'));
      return false;
    }

    if (!template.trim()) {
      toast.error(t('validation.templateRequired'));
      return false;
    }

    return true;
  };

  // 保存
  const handleSave = () => {
    if (!validate()) return;

    if (command) {
      // 更新现有命令
      updateCommand(command.id, {
        name: name.trim(),
        template: template.trim(),
      });
      toast.success(t('success.updated'));
    } else {
      // 创建新命令
      addCommand({
        name: name.trim(),
        template: template.trim(),
      });
      toast.success(t('success.created'));
    }

    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>{command ? t('editTitle') : t('createTitle')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* 命令名 */}
          <div className="space-y-2">
            <Label htmlFor="name">{t('fields.name.label')} *</Label>
            <Input
              id="name"
              placeholder={t('fields.name.placeholder')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
            <p className="text-xs text-muted-foreground">{t('fields.name.hint')}</p>
          </div>

          {/* 指令文本 */}
          <div className="space-y-2">
            <Label htmlFor="template">{t('fields.template.label')} *</Label>
            <Textarea
              id="template"
              placeholder={t('fields.template.placeholder')}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              rows={6}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">{t('fields.template.hint')}</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('actions.cancel')}
          </Button>
          <Button onClick={handleSave}>{t('actions.save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
