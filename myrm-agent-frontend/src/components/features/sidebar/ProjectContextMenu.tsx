'use client';

/**
 * [INPUT]
 * - @/services/projects::Project (POS: 菜单所属的项目)
 *
 * [OUTPUT]
 * - PROJECT_COLORS: 新项目按序取用的调色板，也是菜单里可选的颜色
 * - ProjectContextMenu: 项目芯片的右键 / 长按菜单：重命名、颜色、工作目录、默认智能体、删除
 *
 * [POS]
 * 菜单以指针为左上角，再按自身尺寸收回到视口内，靠右或靠下打开时不被截断；
 * 宽度取内容宽度（`w-max`）：固定定位的默认宽度只算到视口右缘，靠右打开时会被压窄，五列色块会叠在一起。
 * 点击目标：指针设备条目 28px、色块 24px；手机条目 44px、色块 40px（色块画面 16px / 24px，其余是点击区域）。
 */
import type { CSSProperties, Ref } from 'react';
import { Bot, FolderCog, Pencil, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { Project } from '@/services/projects';

export const PROJECT_COLORS = [
  '#7cb9ff',
  '#ff7eb3',
  '#7afcb4',
  '#ffd97c',
  '#c4b5fd',
  '#fb923c',
  '#67e8f9',
  '#f87171',
  '#a3e635',
  '#e879f9',
];

const VIEWPORT_GAP_PX = 8;

/**
 * `100%` 是菜单自身的宽高：只有右缘或下缘会超出视口时 `min(0px, …)` 才取负值，把菜单整体移回，
 * 所以不需要先量菜单尺寸。
 */
const clampedToViewport = (x: number, y: number): CSSProperties => ({
  left: x,
  top: y,
  transform: `translate(min(0px, calc(100vw - ${x}px - 100% - ${VIEWPORT_GAP_PX}px)), min(0px, calc(100dvh - ${y}px - 100% - ${VIEWPORT_GAP_PX}px)))`,
});

interface ProjectContextMenuProps {
  ref: Ref<HTMLDivElement>;
  project: Project;
  x: number;
  y: number;
  isMobile: boolean;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
  onChangeColor: (project: Project, color: string) => void;
  onSetWorkspace: (project: Project) => void;
  onSetDefaultAgent: (project: Project) => void;
}

export function ProjectContextMenu({
  ref,
  project,
  x,
  y,
  isMobile,
  onEdit,
  onDelete,
  onChangeColor,
  onSetWorkspace,
  onSetDefaultAgent,
}: ProjectContextMenuProps) {
  const t = useTranslations();
  const item = cn(
    'w-full flex items-center gap-2 px-3 transition-colors text-left',
    isMobile ? 'min-h-11 py-3' : 'py-1.5',
  );
  const neutralItem = cn(item, 'hover:bg-black/5 dark:hover:bg-white/5');

  return (
    <div
      ref={ref}
      className="fixed z-50 w-max min-w-[140px] rounded-lg border border-border/50 bg-popover/95 backdrop-blur-sm shadow-lg py-1 text-xs"
      style={clampedToViewport(x, y)}
    >
      <button className={neutralItem} onClick={() => onEdit(project)}>
        <Pencil size={12} /> {t('project.rename')}
      </button>
      <button className={neutralItem} onClick={() => onSetWorkspace(project)}>
        <FolderCog size={12} /> {t('project.setWorkspace')}
      </button>
      <button className={neutralItem} onClick={() => onSetDefaultAgent(project)}>
        <Bot size={12} /> {t('project.setDefaultAgent')}
      </button>
      <div className="grid grid-cols-5 justify-items-center gap-1 px-3 py-1.5">
        {PROJECT_COLORS.map((c) => (
          <button
            key={c}
            aria-label={c}
            aria-pressed={project.color === c}
            onClick={() => onChangeColor(project, c)}
            className={cn('group flex items-center justify-center rounded-full', isMobile ? 'size-10' : 'size-6')}
          >
            <span
              className={cn(
                'rounded-full transition-transform group-hover:scale-125',
                isMobile ? 'size-6' : 'size-4',
                project.color === c && 'ring-2 ring-offset-1 ring-foreground/30',
              )}
              style={{ backgroundColor: c }}
            />
          </button>
        ))}
      </div>
      <div className="my-0.5 border-t border-border/30" />
      <button className={cn(item, 'hover:bg-destructive/10 text-destructive-text')} onClick={() => onDelete(project)}>
        <Trash2 size={12} /> {t('project.delete')}
      </button>
    </div>
  );
}
