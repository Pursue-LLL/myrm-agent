/**
 * CLI 工作路径组件
 *
 * 提供工作路径的输入、编辑、浏览和最近项目选择功能
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - @/utils/pathValidation::isAbsolutePath, normalizePath (POS: 路径验证工具)
 * - @/lib/tauri::isTauriEnvironment (POS: Tauri 环境检测)
 * - @tauri-apps/plugin-dialog::open (POS: 原生文件夹选择对话框)
 * - ./constants::CLI_RECENT_PROJECTS_STORAGE_KEY, MAX_RECENT_PROJECTS (POS: CLI 常量配置)
 *
 * [OUTPUT]
 * - CLIWorkingDirectory: CLI 智能体工作路径管理组件
 *   - 编辑模式：输入框 + 浏览按钮 + 最近项目下拉
 *   - 显示模式：项目名 + 完整路径 + 编辑按钮
 *
 * [POS]
 * CLI 智能体的工作路径管理组件。独立封装工作路径的输入、验证、
 * 原生文件夹选择、最近项目列表等功能。从 PresetAgentCard 拆分出来，
 * 符合单一职责原则，可在其他需要项目路径选择的场景复用。
 */

import { useState, useEffect, useCallback, useRef, useMemo, memo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { FolderOpen, Check, Pencil, FolderSearch, Clock } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { isAbsolutePath, normalizePath } from '@/utils/pathValidation';
import { CLI_RECENT_PROJECTS_STORAGE_KEY, MAX_RECENT_PROJECTS } from './constants';
import { isTauriEnvironment } from '@/lib/tauri';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface CLIWorkingDirectoryProps {
  /** 当前工作目录 */
  workingDirectory?: string;
  /** 工作目录变更回调 */
  onWorkingDirectoryChange?: (directory: string) => void;
}

/**
 * CLI 工作路径组件
 *
 * 功能：
 * - 工作路径输入/编辑
 * - Tauri 原生文件夹选择器
 * - 最近项目列表
 * - 项目名显示（而非完整路径）
 */
const CLIWorkingDirectory = memo<CLIWorkingDirectoryProps>(({ workingDirectory, onWorkingDirectoryChange }) => {
  const t = useTranslations('presetAgent');

  // 编辑模式状态
  const [isEditing, setIsEditing] = useState(!workingDirectory);
  const [inputValue, setInputValue] = useState(workingDirectory || '');
  const [error, setError] = useState<string | null>(null);
  const [recentProjects, setRecentProjects] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // 从 localStorage 加载最近项目
  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const stored = localStorage.getItem(CLI_RECENT_PROJECTS_STORAGE_KEY);
      if (stored) {
        setRecentProjects(JSON.parse(stored));
      }
    } catch {
      // ignore
    }
  }, []);

  // 保存最近项目到 localStorage
  const saveToRecentProjects = useCallback((path: string) => {
    if (!path) return;
    setRecentProjects((prev) => {
      const filtered = prev.filter((p) => p !== path);
      const updated = [path, ...filtered].slice(0, MAX_RECENT_PROJECTS);
      try {
        localStorage.setItem(CLI_RECENT_PROJECTS_STORAGE_KEY, JSON.stringify(updated));
      } catch {
        // ignore
      }
      return updated;
    });
  }, []);

  // 从路径获取项目名（最后一级目录）
  const getProjectName = useMemo(() => {
    return (path: string) => {
      if (!path) return '';
      const parts = path.replace(/\/$/, '').split(/[/\\]/);
      return parts[parts.length - 1] || path;
    };
  }, []);

  // 当外部 workingDirectory 变化时同步
  useEffect(() => {
    setInputValue(workingDirectory || '');
    if (workingDirectory) {
      setIsEditing(false);
    }
  }, [workingDirectory]);

  // 处理输入框点击，阻止事件冒泡
  const handleInputClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
  }, []);

  // 处理输入框变化
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
    setError(null);
  }, []);

  // 保存工作路径
  const handleSave = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const normalizedValue = normalizePath(inputValue);

      if (!normalizedValue) {
        setError(t('errors.workingDirectoryRequired'));
        return;
      }

      if (!isAbsolutePath(normalizedValue)) {
        setError(t('invalidAbsolutePath'));
        return;
      }

      setError(null);
      setInputValue(normalizedValue);
      onWorkingDirectoryChange?.(normalizedValue);
      saveToRecentProjects(normalizedValue);
      setIsEditing(false);
    },
    [inputValue, onWorkingDirectoryChange, t, saveToRecentProjects],
  );

  // 进入编辑模式
  const handleEdit = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsEditing(true);
    setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
  }, []);

  // 打开文件夹选择器
  const handleBrowse = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();

      if (!isTauriEnvironment()) return;

      try {
        const { open } = await import('@tauri-apps/plugin-dialog');
        const selected = await open({
          directory: true,
          multiple: false,
          title: t('selectWorkingDirectory'),
        });

        if (selected && typeof selected === 'string') {
          const normalizedPath = normalizePath(selected);
          setInputValue(normalizedPath);
          setError(null);
          onWorkingDirectoryChange?.(normalizedPath);
          saveToRecentProjects(normalizedPath);
          setIsEditing(false);
        }
      } catch (err) {
        console.error('Failed to open folder picker:', err);
      }
    },
    [onWorkingDirectoryChange, t, saveToRecentProjects],
  );

  // 选择最近项目
  const handleSelectRecentProject = useCallback(
    (path: string) => {
      const normalizedPath = normalizePath(path);
      setInputValue(normalizedPath);
      setError(null);
      onWorkingDirectoryChange?.(normalizedPath);
      saveToRecentProjects(normalizedPath);
      setIsEditing(false);
    },
    [onWorkingDirectoryChange, saveToRecentProjects],
  );

  // 处理按键
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.nativeEvent.isComposing) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSave(e as unknown as React.MouseEvent);
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setInputValue(workingDirectory || '');
        setError(null);
        if (workingDirectory) {
          setIsEditing(false);
        }
      }
    },
    [handleSave, workingDirectory],
  );

  // 失焦处理
  const handleBlur = useCallback(() => {
    const normalizedValue = normalizePath(inputValue);

    if (!normalizedValue && workingDirectory) {
      setInputValue(workingDirectory);
      setError(null);
      setIsEditing(false);
      return;
    }

    if (normalizedValue && isAbsolutePath(normalizedValue)) {
      setError(null);
      setInputValue(normalizedValue);
      onWorkingDirectoryChange?.(normalizedValue);
      saveToRecentProjects(normalizedValue);
      setIsEditing(false);
    }
  }, [inputValue, workingDirectory, onWorkingDirectoryChange, saveToRecentProjects]);

  return (
    <div className="space-y-1 pt-2 border-t border-border/30" onClick={handleInputClick}>
      {isEditing ? (
        /* 编辑模式 */
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <FolderOpen size={14} className="text-muted-foreground shrink-0" />
            <Input
              ref={inputRef}
              value={inputValue}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              onClick={handleInputClick}
              onBlur={handleBlur}
              placeholder={t('workingDirectoryPlaceholder')}
              className={cn(
                'h-7 text-xs flex-1',
                'bg-background/50 border-border/50',
                'focus:border-primary/50 focus:ring-1 focus:ring-primary/20',
                error && 'border-destructive focus:border-destructive focus:ring-destructive/20',
              )}
            />
            {/* 浏览按钮（仅 Tauri 模式显示） */}
            {isTauriEnvironment() && (
              <button
                type="button"
                onClick={handleBrowse}
                className={cn(
                  'p-1.5 rounded-full shrink-0',
                  'hover:bg-muted/50 text-muted-foreground',
                  'transition-colors duration-200',
                )}
                title={t('browse')}
              >
                <FolderSearch size={14} />
              </button>
            )}
            {/* 最近项目下拉菜单 */}
            {recentProjects.length > 0 && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    onClick={handleInputClick}
                    className={cn(
                      'p-1.5 rounded-full shrink-0',
                      'hover:bg-muted/50 text-muted-foreground',
                      'transition-colors duration-200',
                    )}
                    title={t('recentProjects')}
                  >
                    <Clock size={14} />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-[280px]">
                  {recentProjects.map((path) => (
                    <DropdownMenuItem
                      key={path}
                      onClick={() => handleSelectRecentProject(path)}
                      className="flex flex-col items-start gap-0.5 py-2"
                    >
                      <span className="text-xs font-medium">{getProjectName(path)}</span>
                      <span className="text-[10px] text-muted-foreground truncate w-full">{path}</span>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            <button
              type="button"
              onClick={handleSave}
              className={cn(
                'p-1.5 rounded-full shrink-0',
                'bg-primary/10 hover:bg-primary/20 text-primary',
                'transition-colors duration-200',
              )}
              title={t('confirm')}
            >
              <Check size={14} />
            </button>
          </div>
        </div>
      ) : (
        /* 显示模式 - 显示项目名，hover 显示完整路径 */
        <div className="flex items-center gap-1.5">
          <FolderOpen size={14} className="text-muted-foreground shrink-0" />
          <span className="text-[11px] text-muted-foreground truncate flex-1 font-medium" title={workingDirectory}>
            {getProjectName(workingDirectory || '')}
          </span>
          <span className="text-[10px] text-muted-foreground/60 truncate max-w-[120px] hidden sm:inline">
            {workingDirectory}
          </span>
          <button
            type="button"
            onClick={handleEdit}
            className={cn(
              'p-1 rounded-full shrink-0',
              'hover:bg-muted/50 text-muted-foreground',
              'transition-colors duration-200',
            )}
            title={t('edit') || 'Edit'}
          >
            <Pencil size={12} />
          </button>
        </div>
      )}
      {/* 错误提示 */}
      {error && <p className="text-[10px] text-destructive pl-5">{error}</p>}
    </div>
  );
});

CLIWorkingDirectory.displayName = 'CLIWorkingDirectory';

export default CLIWorkingDirectory;
