/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线，当前会话与会话列表)
 * - @/store/useProjectStore::useProjectStore (POS: 项目列表与工作区路径)
 *
 * [OUTPUT]
 * - useHideChatWorkspacePicker: 当前会话所属项目是否已设置工作区路径。
 *
 * [POS]
 * 会话属于一个设置了工作区路径的项目时，输入区不显示目录选择行（WorkspaceDirPicker）。项目列表未加载时在此触发加载。
 */
import { useEffect, useMemo } from 'react';

import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';

export function useHideChatWorkspacePicker(): boolean {
  const chatId = useChatStore((s) => s.chatId);
  const chatHistoryItems = useChatStore((s) => s.chatHistoryItems);
  const projects = useProjectStore((s) => s.projects);
  const projectsLoaded = useProjectStore((s) => s.loaded);
  const fetchProjects = useProjectStore((s) => s.fetchProjects);

  useEffect(() => {
    if (!projectsLoaded) {
      void fetchProjects();
    }
  }, [fetchProjects, projectsLoaded]);

  return useMemo(() => {
    if (!chatId) {
      return false;
    }
    const projectId = chatHistoryItems.find((item) => item.id === chatId)?.projectId;
    if (!projectId) {
      return false;
    }
    const project = projects.find((item) => item.id === projectId);
    return Boolean(project?.workspacePath?.trim());
  }, [chatHistoryItems, chatId, projects]);
}
