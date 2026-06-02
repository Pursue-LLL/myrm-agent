/**
 * 命令面板组件（Cursor 风格）
 *
 * 在输入框上方显示可用的快捷指令，设计参考 Cursor
 */

'use client';

import * as React from 'react';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverAnchor } from '@/components/ui/popover';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import type { SlashAction, SlashCommand, SlashItem } from '@/types/command';
import { useCommandStore } from '@/store/useCommandStore';
import { cn } from '@/lib/utils/classnameUtils';
import { Zap, Plus, Command as CommandIcon } from 'lucide-react';

interface CommandPaletteProps {
  /** 是否显示 */
  open: boolean;
  /** 过滤后的命令列表 */
  items: SlashItem[];
  /** 当前选中的索引 */
  selectedIndex: number;
  /** 选择命令回调 */
  onSelect: (item: SlashItem) => void;
  /** 锚点元素（输入框） */
  anchorEl?: HTMLElement | null;
}

function isSlashAction(item: SlashItem): item is SlashAction {
  return item.type === 'action';
}

function isSlashCommand(item: SlashItem): item is SlashCommand {
  return item.type === 'command';
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ open, items, selectedIndex, onSelect, anchorEl }) => {
  const t = useTranslations('commands');
  const router = useRouter();
  const listRef = React.useRef<HTMLDivElement>(null);
  const { recentCommandIds } = useCommandStore();

  // 自动滚动到选中项
  React.useEffect(() => {
    if (listRef.current && selectedIndex >= 0) {
      const selectedItem = listRef.current.children[selectedIndex] as HTMLElement;
      if (selectedItem) {
        selectedItem.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedIndex]);

  if (!open) return null;

  // 分组命令
  const systemActions = items.filter(
    (item): item is SlashAction => isSlashAction(item) && !item.id.startsWith('skill:'),
  );
  const skillActions = items.filter((item): item is SlashAction => isSlashAction(item) && item.id.startsWith('skill:'));
  const commands = items.filter(isSlashCommand);

  // 最近使用的命令（取前3个）
  const recentCommands = recentCommandIds
    .slice(0, 3)
    .map((id) => commands.find((cmd) => cmd.id === id))
    .filter((item): item is SlashCommand => item !== undefined);

  // 其他命令（排除最近使用的）
  const otherCommands = commands.filter((cmd) => !recentCommandIds.includes(cmd.id));

  return (
    <Popover open={open} modal={false}>
      {anchorEl && <PopoverAnchor virtualRef={{ current: anchorEl }} />}
      <PopoverContent
        className="w-[420px] p-0 shadow-xl border-border/50"
        side="top"
        align="start"
        sideOffset={8}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <Command className="rounded-lg">
          <CommandList ref={listRef} className="max-h-[400px] overflow-y-auto">
            {items.length === 0 ? (
              <CommandEmpty>
                <div className="py-8 text-center text-sm">
                  <Zap className="w-12 h-12 mx-auto mb-3 text-muted-foreground/40" />
                  <p className="text-muted-foreground mb-1">{t('palette.noCommands')}</p>
                  <p className="text-xs text-muted-foreground/70 mb-4">{t('palette.goToSettings')}</p>
                  <button
                    onClick={() => router.push('/settings/personalization')}
                    className="inline-flex items-center gap-2 text-xs text-primary hover:text-primary/80 transition-colors"
                  >
                    <Plus className="w-3 h-3" />
                    {t('palette.createCommand')}
                  </button>
                </div>
              </CommandEmpty>
            ) : (
              <>
                {/* 最近使用 */}
                {recentCommands.length > 0 && (
                  <>
                    <CommandGroup heading={t('palette.recentlyUsed')} className="pb-2">
                      {recentCommands.map((item) => {
                        const globalIndex = items.indexOf(item);
                        const isSelected = globalIndex === selectedIndex;

                        return (
                          <CommandItem
                            key={item.id}
                            value={item.id}
                            onSelect={() => onSelect(item)}
                            className={cn(
                              'flex items-center gap-3 px-3 py-2.5 mx-1 rounded-full cursor-pointer transition-all',
                              'hover:bg-accent/50',
                              isSelected && 'bg-accent',
                            )}
                          >
                            <Zap className="w-4 h-4 text-muted-foreground shrink-0" />
                            <div className="flex-1 min-w-0 flex items-center justify-between">
                              <div className="min-w-0">
                                <div className="font-medium text-sm flex items-center gap-2">
                                  <span>/{item.name}</span>
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                    {t('palette.commandType')}
                                  </span>
                                </div>
                                <div className="text-xs text-muted-foreground/70 truncate mt-0.5">{item.template}</div>
                              </div>
                            </div>
                          </CommandItem>
                        );
                      })}
                    </CommandGroup>
                    <CommandSeparator />
                  </>
                )}

                {/* 系统行为 */}
                {systemActions.length > 0 && (
                  <>
                    <CommandGroup heading={t('palette.actions')} className="py-2">
                      {systemActions.map((item) => {
                        const globalIndex = items.indexOf(item);
                        const isSelected = globalIndex === selectedIndex;

                        return (
                          <CommandItem
                            key={item.id}
                            value={item.id}
                            onSelect={() => onSelect(item)}
                            className={cn(
                              'flex items-center gap-3 px-3 py-2.5 mx-1 rounded-full cursor-pointer transition-all',
                              'hover:bg-accent/50',
                              isSelected && 'bg-accent',
                            )}
                          >
                            <CommandIcon className="w-4 h-4 text-muted-foreground shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-sm flex items-center gap-2">
                                <span>/{item.name}</span>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                  {t('palette.actionType')}
                                </span>
                              </div>
                              <div className="text-xs text-muted-foreground/70 truncate mt-0.5">
                                {item.id.startsWith('builtin:') ? t(`builtin.${item.id.slice(8)}`) : item.description}
                              </div>
                            </div>
                          </CommandItem>
                        );
                      })}
                    </CommandGroup>
                    <CommandSeparator />
                  </>
                )}

                {/* 技能快捷触发 */}
                {skillActions.length > 0 && (
                  <>
                    <CommandGroup heading={t('palette.skills')} className="py-2">
                      {skillActions.map((item) => {
                        const globalIndex = items.indexOf(item);
                        const isSelected = globalIndex === selectedIndex;

                        return (
                          <CommandItem
                            key={item.id}
                            value={item.id}
                            onSelect={() => onSelect(item)}
                            className={cn(
                              'flex items-center gap-3 px-3 py-2.5 mx-1 rounded-full cursor-pointer transition-all',
                              'hover:bg-accent/50',
                              isSelected && 'bg-accent',
                            )}
                          >
                            <Zap className="w-4 h-4 text-amber-500 shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-sm flex items-center gap-2">
                                <span>/{item.name}</span>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400">
                                  {t('palette.skillType')}
                                </span>
                              </div>
                              <div className="text-xs text-muted-foreground/70 truncate mt-0.5">{item.description}</div>
                            </div>
                          </CommandItem>
                        );
                      })}
                    </CommandGroup>
                    {(otherCommands.length > 0 || recentCommands.length === 0) && <CommandSeparator />}
                  </>
                )}

                {/* 其他命令 */}
                {otherCommands.length > 0 && (
                  <CommandGroup heading={t('palette.commands')} className="py-2">
                    {otherCommands.map((item) => {
                      const globalIndex = items.indexOf(item);
                      const isSelected = globalIndex === selectedIndex;

                      return (
                        <CommandItem
                          key={item.id}
                          value={item.id}
                          onSelect={() => onSelect(item)}
                          className={cn(
                            'flex items-center gap-3 px-3 py-2.5 mx-1 rounded-full cursor-pointer transition-all',
                            'hover:bg-accent/50',
                            isSelected && 'bg-accent',
                          )}
                        >
                          <Zap className="w-4 h-4 text-muted-foreground shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-sm flex items-center gap-2">
                              <span>/{item.name}</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                {t('palette.commandType')}
                              </span>
                            </div>
                            <div className="text-xs text-muted-foreground/70 truncate mt-0.5">{item.template}</div>
                          </div>
                        </CommandItem>
                      );
                    })}
                  </CommandGroup>
                )}

                {/* 创建命令入口 */}
                <CommandSeparator />
                <div className="p-2">
                  <button
                    onClick={() => router.push('/settings/personalization')}
                    className={cn(
                      'flex items-center gap-3 w-full px-3 py-2.5 rounded-full cursor-pointer transition-all',
                      'text-sm text-muted-foreground hover:text-foreground',
                      'hover:bg-accent/30',
                    )}
                  >
                    <Plus className="w-4 h-4 shrink-0" />
                    <span>{t('palette.createCommand')}</span>
                  </button>
                </div>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};
