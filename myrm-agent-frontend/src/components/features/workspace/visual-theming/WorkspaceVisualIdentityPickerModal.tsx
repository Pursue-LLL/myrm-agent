import React, { useEffect, useState } from 'react';
import {
  BookOpen,
  Briefcase,
  Check,
  Code2,
  Database,
  Film,
  Gamepad2,
  Palette,
  Terminal,
  X,
} from 'lucide-react';
import { getColorClasses } from './workspaceThemingEngine';
import {
  WorkspaceSemanticIcon,
  WorkspaceThemeColor,
  WorkspaceVisualTheme,
} from './workspaceThemingTypes';
import { useWorkspaceThemingStore } from './useWorkspaceThemingStore';

interface WorkspaceVisualIdentityPickerModalProps {
  className?: string;
  onSaved?: (theme: WorkspaceVisualTheme) => void;
}

const AVAILABLE_ICONS: Array<{
  id: WorkspaceSemanticIcon;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { id: 'code', label: '研发代码', icon: Code2 },
  { id: 'briefcase', label: '商业企划', icon: Briefcase },
  { id: 'gamepad', label: '互动游戏', icon: Gamepad2 },
  { id: 'film', label: '影音多媒体', icon: Film },
  { id: 'database', label: '数据中台', icon: Database },
  { id: 'palette', label: '视觉创意', icon: Palette },
  { id: 'book', label: '文档知识', icon: BookOpen },
  { id: 'terminal', label: '运维工控', icon: Terminal },
];

const AVAILABLE_COLORS: Array<{
  id: WorkspaceThemeColor;
  label: string;
  bgHex: string;
}> = [
  { id: 'violet', label: '紫罗兰', bgHex: 'bg-violet-500' },
  { id: 'blue', label: '蔚蓝', bgHex: 'bg-blue-500' },
  { id: 'emerald', label: '翡翠绿', bgHex: 'bg-emerald-500' },
  { id: 'amber', label: '琥珀黄', bgHex: 'bg-amber-500' },
  { id: 'rose', label: '玫瑰红', bgHex: 'bg-rose-500' },
  { id: 'indigo', label: '靛蓝', bgHex: 'bg-indigo-500' },
  { id: 'slate', label: '石板灰', bgHex: 'bg-slate-500' },
];

export const WorkspaceVisualIdentityPickerModal: React.FC<
  WorkspaceVisualIdentityPickerModalProps
> = ({ className = '', onSaved }) => {
  const isModalOpen = useWorkspaceThemingStore(
    (state) => state.isCustomizeThemeModalOpen,
  );
  const editingWorkspaceId = useWorkspaceThemingStore(
    (state) => state.editingWorkspaceId,
  );
  const workspaces = useWorkspaceThemingStore((state) => state.workspaces);
  const updateWorkspaceTheme = useWorkspaceThemingStore(
    (state) => state.updateWorkspaceTheme,
  );
  const closeCustomizeThemeModal = useWorkspaceThemingStore(
    (state) => state.closeCustomizeThemeModal,
  );

  const editingWorkspace = editingWorkspaceId
    ? workspaces[editingWorkspaceId]
    : undefined;

  const [selectedIcon, setSelectedIcon] =
    useState<WorkspaceSemanticIcon>('code');
  const [selectedColor, setSelectedColor] =
    useState<WorkspaceThemeColor>('violet');
  const [customLabel, setCustomLabel] = useState<string>('');

  useEffect(() => {
    if (editingWorkspace) {
      setSelectedIcon(editingWorkspace.theme.icon);
      setSelectedColor(editingWorkspace.theme.color);
      setCustomLabel(editingWorkspace.theme.customLabel ?? '');
    }
  }, [editingWorkspace]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isModalOpen) {
        closeCustomizeThemeModal();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isModalOpen, closeCustomizeThemeModal]);

  if (!isModalOpen || !editingWorkspace) {
    return null;
  }

  const colorClasses = getColorClasses(selectedColor);
  const ActiveIconComp =
    AVAILABLE_ICONS.find((i) => i.id === selectedIcon)?.icon ?? Code2;

  const handleSave = () => {
    const newTheme: WorkspaceVisualTheme = {
      icon: selectedIcon,
      color: selectedColor,
      customLabel: customLabel.trim() || undefined,
    };
    updateWorkspaceTheme(editingWorkspace.id, newTheme);
    if (onSaved) {
      onSaved(newTheme);
    }
    closeCustomizeThemeModal();
  };

  return (
    <dialog
      open
      aria-label="工作区语义图标与主题色彩定制对话框"
      className="fixed inset-0 z-50 m-0 flex h-full w-full items-center justify-center border-0 bg-background/80 p-4 backdrop-blur-md"
    >
      <div
        data-testid="workspace-theming-modal"
        className={`w-full max-w-lg rounded-2xl border border-border/80 bg-background p-5 shadow-2xl ${className}`}
      >
        {/* 标题 */}
        <div className="flex items-center justify-between border-b border-border/40 pb-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              工作区专属视觉标识定制
            </h3>
            <p className="text-xs text-muted-foreground">
              为《{editingWorkspace.name}》自选语义图标与 Tailwind 主题色彩
            </p>
          </div>
          <button
            type="button"
            onClick={closeCustomizeThemeModal}
            aria-label="关闭自选面板"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 主体自选区 */}
        <div className="mt-4 space-y-4 text-xs">
          {/* 实时效果预览 */}
          <div className="rounded-xl border border-border/60 bg-muted/20 p-3">
            <span className="block text-[11px] font-medium text-muted-foreground mb-1.5">
              侧边栏与卡片微标实时预览:
            </span>
            <div className="flex items-center gap-2.5 rounded-lg border border-border/50 bg-background p-2.5">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-lg border ${colorClasses.bgClass} ${colorClasses.borderClass} ${colorClasses.textClass}`}
              >
                <ActiveIconComp className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-foreground truncate">
                    {editingWorkspace.name}
                  </span>
                  {customLabel.trim() && (
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium border ${colorClasses.bgClass} ${colorClasses.borderClass} ${colorClasses.textClass}`}
                    >
                      {customLabel.trim()}
                    </span>
                  )}
                </div>
                <span className="text-[11px] font-mono text-muted-foreground truncate block">
                  {editingWorkspace.path}
                </span>
              </div>
            </div>
          </div>

          {/* 语义图标选择矩阵 */}
          <div>
            <span className="block font-medium text-foreground mb-2">
              1. 选择工作区语义图标
            </span>
            <div className="grid grid-cols-4 gap-2">
              {AVAILABLE_ICONS.map((item) => {
                const IconComp = item.icon;
                const isSelected = selectedIcon === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setSelectedIcon(item.id);
                    }}
                    className={`flex flex-col items-center justify-center gap-1 rounded-xl border p-2.5 transition-all ${
                      isSelected
                        ? 'border-primary bg-primary/10 text-primary shadow-xs ring-1 ring-primary'
                        : 'border-border/60 bg-background text-muted-foreground hover:bg-muted hover:text-foreground'
                    }`}
                  >
                    <IconComp className="h-4 w-4" />
                    <span className="text-[10px] font-medium">
                      {item.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 主题色自选色环 */}
          <div>
            <span className="block font-medium text-foreground mb-2">
              2. 选择 Tailwind 主题色彩
            </span>
            <div className="flex flex-wrap items-center gap-2.5">
              {AVAILABLE_COLORS.map((col) => {
                const isSelected = selectedColor === col.id;
                return (
                  <button
                    key={col.id}
                    type="button"
                    onClick={() => {
                      setSelectedColor(col.id);
                    }}
                    aria-label={`选择${col.label}色`}
                    className={`relative flex h-7 w-7 items-center justify-center rounded-full transition-transform hover:scale-110 ${col.bgHex} ${
                      isSelected ? 'ring-2 ring-primary ring-offset-2' : ''
                    }`}
                  >
                    {isSelected && (
                      <Check className="h-3.5 w-3.5 text-white" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 自定义微标签 */}
          <div>
            <label
              htmlFor="custom-label-input"
              className="block font-medium text-foreground mb-1"
            >
              3. 专属角标文字 (选填，限 6 字以内)
            </label>
            <input
              id="custom-label-input"
              type="text"
              maxLength={6}
              value={customLabel}
              onChange={(e) => {
                setCustomLabel(e.target.value);
              }}
              placeholder="例如: 架构重构 / 商业企划"
              className="h-8 w-full rounded-lg border border-border/70 bg-background px-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-hidden focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        {/* 底部按钮栏 */}
        <div className="mt-5 flex items-center justify-end gap-2 border-t border-border/40 pt-3">
          <button
            type="button"
            onClick={closeCustomizeThemeModal}
            className="rounded-lg border border-border/70 px-3.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
          >
            保存并应用主题
          </button>
        </div>
      </div>
    </dialog>
  );
};
