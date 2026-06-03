'use client';

/**
 * [INPUT] @/store/useProjectStore, @/services/projects
 * [OUTPUT] ProjectBar: 侧边栏项目过滤芯片栏
 * [POS] 在 source filter 下方渲染可选彩色项目芯片，支持点击过滤、添加和管理项目。
 */

import { useCallback, useState, useRef, useEffect } from 'react';
import { Plus, Pencil, Trash2, FolderOpen } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useProjectStore } from '@/store/useProjectStore';
import type { Project } from '@/services/projects';
import { useTranslations } from 'next-intl';

const PROJECT_COLORS = [
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

interface ProjectBarProps {
  isMobile?: boolean;
}

export default function ProjectBar({ isMobile }: ProjectBarProps) {
  const t = useTranslations();
  const { projects, activeFilter, loaded, fetchProjects, setActiveFilter, addProject, updateProject, removeProject } =
    useProjectStore();
  const [showInput, setShowInput] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [contextMenu, setContextMenu] = useState<{ projectId: string; x: number; y: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loaded) fetchProjects();
  }, [loaded, fetchProjects]);

  useEffect(() => {
    if (showInput) inputRef.current?.focus();
  }, [showInput]);

  useEffect(() => {
    if (editingId) editInputRef.current?.focus();
  }, [editingId]);

  useEffect(() => {
    if (!contextMenu) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [contextMenu]);

  const handleAddSubmit = useCallback(async () => {
    const name = inputValue.trim();
    if (!name) {
      setShowInput(false);
      return;
    }
    const color = PROJECT_COLORS[projects.length % PROJECT_COLORS.length];
    await addProject(name, color);
    setInputValue('');
    setShowInput(false);
  }, [inputValue, projects.length, addProject]);

  const handleEditSubmit = useCallback(async () => {
    if (!editingId) return;
    const name = editingName.trim();
    if (name) await updateProject(editingId, { name });
    setEditingId(null);
    setEditingName('');
  }, [editingId, editingName, updateProject]);

  const handleDelete = useCallback(
    async (id: string) => {
      await removeProject(id);
      setContextMenu(null);
    },
    [removeProject],
  );

  const handleChipClick = useCallback(
    (projectId: string) => {
      setActiveFilter(activeFilter === projectId ? undefined : projectId);
    },
    [activeFilter, setActiveFilter],
  );

  const handleContextMenu = useCallback((e: React.MouseEvent, projectId: string) => {
    e.preventDefault();
    setContextMenu({ projectId, x: e.clientX, y: e.clientY });
  }, []);

  if (projects.length === 0 && !showInput) {
    return (
      <div className="flex items-center px-2 pb-1">
        <button
          onClick={() => setShowInput(true)}
          className={cn(
            'flex items-center gap-1 text-[10px] text-muted-foreground/60 hover:text-muted-foreground transition-colors',
            isMobile && 'text-[9px]',
          )}
        >
          <FolderOpen size={10} />
          <span>{t('project.addFirst')}</span>
        </button>
      </div>
    );
  }

  return (
    <div className="px-2 pb-1.5">
      <div className="flex items-center gap-1 flex-wrap">
        {/* All filter chip */}
        <ChipButton active={activeFilter === undefined} onClick={() => setActiveFilter(undefined)} isMobile={isMobile}>
          {t('project.all')}
        </ChipButton>

        {/* Unassigned filter */}
        <ChipButton
          active={activeFilter === null}
          onClick={() => setActiveFilter(activeFilter === null ? undefined : null)}
          isMobile={isMobile}
        >
          {t('project.unassigned')}
        </ChipButton>

        {/* Project chips */}
        {projects.map((project) =>
          editingId === project.id ? (
            <input
              key={project.id}
              ref={editInputRef}
              value={editingName}
              onChange={(e) => setEditingName(e.target.value)}
              onBlur={handleEditSubmit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleEditSubmit();
                if (e.key === 'Escape') {
                  setEditingId(null);
                  setEditingName('');
                }
              }}
              className={cn(
                'h-5 px-1.5 text-[10px] rounded-full border border-primary/30 bg-transparent outline-none',
                'w-16 min-w-0',
                isMobile && 'text-[9px] h-4',
              )}
            />
          ) : (
            <ChipButton
              key={project.id}
              active={activeFilter === project.id}
              color={project.color}
              onClick={() => handleChipClick(project.id)}
              onContextMenu={(e) => handleContextMenu(e, project.id)}
              isMobile={isMobile}
            >
              {project.name}
            </ChipButton>
          ),
        )}

        {/* Add button or input */}
        {showInput ? (
          <div className="flex items-center gap-0.5">
            <input
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onBlur={handleAddSubmit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAddSubmit();
                if (e.key === 'Escape') {
                  setShowInput(false);
                  setInputValue('');
                }
              }}
              placeholder={t('project.namePlaceholder')}
              className={cn(
                'h-5 px-1.5 text-[10px] rounded-full border border-primary/30 bg-transparent outline-none placeholder:text-muted-foreground/40',
                'w-16 min-w-0',
                isMobile && 'text-[9px] h-4',
              )}
            />
          </div>
        ) : (
          <button
            onClick={() => setShowInput(true)}
            className="flex items-center justify-center w-5 h-5 rounded-full hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
          >
            <Plus size={10} className="text-muted-foreground/50" />
          </button>
        )}
      </div>

      {/* Context menu */}
      {contextMenu && (
        <ContextMenu
          ref={menuRef}
          project={projects.find((p) => p.id === contextMenu.projectId)!}
          x={contextMenu.x}
          y={contextMenu.y}
          onEdit={(p) => {
            setEditingId(p.id);
            setEditingName(p.name);
            setContextMenu(null);
          }}
          onDelete={(p) => handleDelete(p.id)}
          onChangeColor={async (p, color) => {
            await updateProject(p.id, { color });
            setContextMenu(null);
          }}
          t={t}
        />
      )}
    </div>
  );
}

function ChipButton({
  active,
  color,
  onClick,
  onContextMenu,
  children,
  isMobile,
}: {
  active: boolean;
  color?: string;
  onClick: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
  children: React.ReactNode;
  isMobile?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      onContextMenu={onContextMenu}
      className={cn(
        'h-5 px-2 rounded-full text-[10px] font-medium transition-all whitespace-nowrap select-none',
        'border border-transparent',
        active
          ? color
            ? 'text-white shadow-sm'
            : 'text-[var(--accent-warm-foreground)] shadow-sm'
          : 'text-muted-foreground/70 hover:text-foreground bg-black/4 dark:bg-white/6 hover:bg-black/8 dark:hover:bg-white/10',
        isMobile && 'text-[9px] h-4 px-1.5',
      )}
      style={
        active && color
          ? { backgroundColor: color, borderColor: color }
          : active
            ? { backgroundColor: 'var(--accent-warm)', borderColor: 'var(--accent-warm)' }
            : undefined
      }
    >
      {color && !active && (
        <span className="inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle" style={{ backgroundColor: color }} />
      )}
      {children}
    </button>
  );
}

interface ContextMenuProps {
  project: Project;
  x: number;
  y: number;
  onEdit: (p: Project) => void;
  onDelete: (p: Project) => void;
  onChangeColor: (p: Project, color: string) => void;
  t: ReturnType<typeof useTranslations>;
}

const ContextMenu = ({
  project,
  x,
  y,
  onEdit,
  onDelete,
  onChangeColor,
  t,
  ref,
}: ContextMenuProps & { ref: React.Ref<HTMLDivElement> }) => {
  return (
    <div
      ref={ref}
      className="fixed z-50 min-w-[140px] rounded-lg border border-border/50 bg-popover/95 backdrop-blur-sm shadow-lg py-1 text-xs"
      style={{ left: x, top: y }}
    >
      <button
        className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-left"
        onClick={() => onEdit(project)}
      >
        <Pencil size={12} /> {t('project.rename')}
      </button>
      <div className="px-3 py-1.5">
        <div className="flex gap-1 flex-wrap">
          {PROJECT_COLORS.map((c) => (
            <button
              key={c}
              onClick={() => onChangeColor(project, c)}
              className={cn(
                'w-4 h-4 rounded-full transition-transform hover:scale-125',
                project.color === c && 'ring-2 ring-offset-1 ring-foreground/30',
              )}
              style={{ backgroundColor: c }}
            />
          ))}
        </div>
      </div>
      <div className="my-0.5 border-t border-border/30" />
      <button
        className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-destructive/10 text-destructive transition-colors text-left"
        onClick={() => onDelete(project)}
      >
        <Trash2 size={12} /> {t('project.delete')}
      </button>
    </div>
  );
};
