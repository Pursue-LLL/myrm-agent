/**
 * 命令设置页面
 *
 * 用户管理自定义命令
 */

'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { useCommandStore } from '@/store/useCommandStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { IconPlus, IconTrash, IconEdit, IconSearch } from '@/components/ui/icons/PremiumIcons';
import { CommandEditor } from './CommandEditor';
import { toast } from '@/lib/utils/toast';
import type { SlashCommand } from '@/types/command';

export const CommandSettings = () => {
  const t = useTranslations('settings.commands');
  const { commands, deleteCommand } = useCommandStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [showEditor, setShowEditor] = useState(false);
  const [editingCommand, setEditingCommand] = useState<SlashCommand | null>(null);

  // 过滤命令
  const filteredCommands = searchQuery
    ? commands.filter(
        (cmd) =>
          cmd.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          cmd.template.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : commands;

  // 删除
  const handleDelete = (id: string, name: string) => {
    if (confirm(t('delete.confirm', { name }))) {
      deleteCommand(id);
      toast.success(t('delete.success'));
    }
  };

  // 编辑
  const handleEdit = (command: SlashCommand) => {
    setEditingCommand(command);
    setShowEditor(true);
  };

  // 新建
  const handleNew = () => {
    setEditingCommand(null);
    setShowEditor(true);
  };

  return (
    <div className="space-y-6">
      {/* 工具栏 */}
      <div className="flex items-center justify-between gap-4">
        {/* 搜索 */}
        <div className="relative flex-1 max-w-sm">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={t('search.placeholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* 添加按钮 */}
        <Button onClick={handleNew}>
          <IconPlus className="w-4 h-4" />
          {t('actions.add')}
        </Button>
      </div>

      {/* 命令列表 */}
      <div className="space-y-3">
        {filteredCommands.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            {searchQuery ? t('search.noResults') : t('empty')}
          </div>
        ) : (
          filteredCommands.map((command) => (
            <div
              key={command.id}
              className="flex items-start justify-between p-4 border rounded-lg bg-card hover:bg-accent/50 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <code className="text-sm font-semibold text-primary">/{command.name}</code>
                </div>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{command.template}</p>
              </div>

              <div className="flex gap-1 ml-4">
                <Button variant="ghost" size="sm" onClick={() => handleEdit(command)}>
                  <IconEdit className="w-4 h-4" />
                </Button>
                <Button variant="ghost" size="sm" onClick={() => handleDelete(command.id, command.name)}>
                  <IconTrash className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 使用提示 */}
      <div className="text-sm text-muted-foreground space-y-2 bg-accent/30 p-4 rounded-lg">
        <p className="font-semibold">{t('tips.title')}</p>
        <ul className="list-disc list-inside space-y-1 ml-2">
          <li>{t('tips.trigger')}</li>
          <li>{t('tips.example')}</li>
        </ul>
      </div>

      {/* 编辑器对话框 */}
      <CommandEditor open={showEditor} onOpenChange={setShowEditor} command={editingCommand} />
    </div>
  );
};
