'use client';

/**
 * [INPUT] @/store/useProjectStore, @/services/projects, ./ProjectChip, ./ProjectContextMenu,
 *         @/components/features/project-workspace/ProjectWorkspaceMount
 * [OUTPUT] ProjectBar: 侧边栏项目过滤芯片栏
 * [POS] 在 source filter 下方渲染可选彩色项目芯片；右键 / 长按打开项目菜单，「设置工作目录」打开 Mount Wizard。
 *       点击目标：指针设备 24px、手机 40px（芯片、新建与接纳按钮同高）。
 */

import { useCallback, useState, useRef, useEffect } from 'react';
import { Plus, FolderOpen, FolderInput } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useProjectStore } from '@/store/useProjectStore';
import type { Project } from '@/services/projects';
import { useTranslations } from 'next-intl';
import ProjectWorkspaceMount from '@/components/features/project-workspace/ProjectWorkspaceMount';
import ProjectWorkspaceAdoptDialog from '@/components/features/project-workspace/ProjectWorkspaceAdoptDialog';
import { ProjectChip, ProjectChipInput } from './ProjectChip';
import { PROJECT_COLORS, ProjectContextMenu } from './ProjectContextMenu';
import { ProjectDefaultAgentDialog } from './ProjectDefaultAgentDialog';

interface ProjectBarProps {
  isMobile?: boolean;
}

export default function ProjectBar({ isMobile = false }: ProjectBarProps) {
  const t = useTranslations();
  const { projects, activeFilter, loaded, fetchProjects, setActiveFilter, addProject, updateProject, removeProject } =
    useProjectStore();
  const [showInput, setShowInput] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [contextMenu, setContextMenu] = useState<{ projectId: string; x: number; y: number } | null>(null);
  const contextMenuProject = contextMenu ? projects.find((p) => p.id === contextMenu.projectId) : undefined;
  const [workspaceMountProject, setWorkspaceMountProject] = useState<Project | null>(null);
  const [defaultAgentProject, setDefaultAgentProject] = useState<Project | null>(null);
  const [adoptDialogOpen, setAdoptDialogOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loaded) {
      fetchProjects();
    }
  }, [loaded, fetchProjects]);

  useEffect(() => {
    if (showInput) {
      inputRef.current?.focus();
    }
  }, [showInput]);

  useEffect(() => {
    if (editingId) {
      editInputRef.current?.focus();
    }
  }, [editingId]);

  useEffect(() => {
    if (!contextMenu) {
      return;
    }
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
    if (!editingId) {
      return;
    }
    const name = editingName.trim();
    if (name) {
      await updateProject(editingId, { name });
    }
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

  const handleWorkspaceBound = useCallback(
    async (_workspacePath: string | null) => {
      await fetchProjects();
      setWorkspaceMountProject(null);
    },
    [fetchProjects],
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
            'flex items-center gap-1.5 rounded-lg px-1.5 text-muted-foreground transition-colors hover:bg-black/4 hover:text-foreground dark:hover:bg-white/6',
            isMobile ? 'h-10 text-xs' : 'h-6 text-[11px] pointer-coarse:h-8',
          )}
        >
          <FolderOpen size={12} />
          <span>{t('project.addFirst')}</span>
        </button>
      </div>
    );
  }

  const adderClass = cn(
    'flex items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-black/5 hover:text-foreground dark:hover:bg-white/5',
    isMobile ? 'size-10' : 'size-6',
  );
  const adderIconSize = isMobile ? 18 : 14;
  const cancelEdit = () => {
    setEditingId(null);
    setEditingName('');
  };
  const cancelAdd = () => {
    setShowInput(false);
    setInputValue('');
  };

  return (
    <div className="px-2 pb-1.5">
      <div className="flex items-center gap-1 flex-wrap">
        {/* All filter chip */}
        <ProjectChip active={activeFilter === undefined} onClick={() => setActiveFilter(undefined)} isMobile={isMobile}>
          {t('project.all')}
        </ProjectChip>

        {/* Unassigned filter */}
        <ProjectChip
          active={activeFilter === null}
          onClick={() => setActiveFilter(activeFilter === null ? undefined : null)}
          isMobile={isMobile}
        >
          {t('project.unassigned')}
        </ProjectChip>

        {/* Project chips */}
        {projects.map((project) =>
          editingId === project.id ? (
            <ProjectChipInput
              key={project.id}
              inputRef={editInputRef}
              value={editingName}
              isMobile={isMobile}
              onChange={setEditingName}
              onSubmit={handleEditSubmit}
              onCancel={cancelEdit}
            />
          ) : (
            <ProjectChip
              key={project.id}
              active={activeFilter === project.id}
              color={project.color}
              onClick={() => handleChipClick(project.id)}
              onContextMenu={(e) => handleContextMenu(e, project.id)}
              isMobile={isMobile}
            >
              {project.name}
            </ProjectChip>
          ),
        )}

        {/* Add button or input */}
        {showInput ? (
          <ProjectChipInput
            inputRef={inputRef}
            value={inputValue}
            placeholder={t('project.namePlaceholder')}
            isMobile={isMobile}
            onChange={setInputValue}
            onSubmit={handleAddSubmit}
            onCancel={cancelAdd}
          />
        ) : (
          <div className="flex items-center gap-1">
            <button onClick={() => setShowInput(true)} title={t('project.newProject')} className={adderClass}>
              <Plus size={adderIconSize} />
            </button>
            <button
              onClick={() => setAdoptDialogOpen(true)}
              title={t('project.workspaceMount.adoptFolder')}
              className={cn(adderClass, 'hover:text-primary')}
            >
              <FolderInput size={adderIconSize} />
            </button>
          </div>
        )}
      </div>

      {/* Context menu */}
      {contextMenu && contextMenuProject && (
        <ProjectContextMenu
          ref={menuRef}
          project={contextMenuProject}
          x={contextMenu.x}
          y={contextMenu.y}
          isMobile={isMobile}
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
          onSetWorkspace={(p) => {
            setWorkspaceMountProject(p);
            setContextMenu(null);
          }}
          onSetDefaultAgent={(p) => {
            setDefaultAgentProject(p);
            setContextMenu(null);
          }}
        />
      )}

      {workspaceMountProject && (
        <ProjectWorkspaceMount
          projectId={workspaceMountProject.id}
          projectName={workspaceMountProject.name}
          initialPath={workspaceMountProject.workspacePath}
          workspaceUsable={workspaceMountProject.workspaceUsable !== false}
          open
          onOpenChange={(nextOpen) => {
            if (!nextOpen) {
              setWorkspaceMountProject(null);
            }
          }}
          onBound={handleWorkspaceBound}
        />
      )}

      {defaultAgentProject && (
        <ProjectDefaultAgentDialog
          open
          onOpenChange={(nextOpen) => {
            if (!nextOpen) {
              setDefaultAgentProject(null);
            }
          }}
          project={defaultAgentProject}
        />
      )}

      {adoptDialogOpen && <ProjectWorkspaceAdoptDialog open={adoptDialogOpen} onOpenChange={setAdoptDialogOpen} />}
    </div>
  );
}
