import { apiRequest } from '@/lib/api';
import type { ChatItem, PaginationInfo } from './chat';

export interface TrashedChatItem extends ChatItem {
  deletedAt: string | null;
}

export interface TrashedChatsResponse {
  items: TrashedChatItem[];
  pagination: PaginationInfo;
}

export const getTrashedChats = async (page: number = 1, pageSize: number = 20): Promise<TrashedChatsResponse> => {
  return apiRequest<TrashedChatsResponse>(`/chats/trash?page=${page}&page_size=${pageSize}`);
};

export const getTrashCount = async (): Promise<number> => {
  const response = await apiRequest<{ count: number }>('/chats/trash/count');
  return response.count;
};

export interface CascadeInfo {
  counts: Record<string, number>;
  total: number;
}

export const getCascadeInfo = async (chatId: string): Promise<CascadeInfo> => {
  return apiRequest<CascadeInfo>(`/chats/trash/${chatId}/cascade-info`);
};

export const restoreChat = async (chatId: string): Promise<void> => {
  await apiRequest(`/chats/trash/${chatId}/restore`, {
    method: 'POST',
  });
};

export const permanentlyDeleteChat = async (chatId: string): Promise<void> => {
  await apiRequest(`/chats/trash/${chatId}`, {
    method: 'DELETE',
  });
};

export const emptyTrash = async (): Promise<number> => {
  const response = await apiRequest<{ deleted_count: number }>('/chats/trash', {
    method: 'DELETE',
  });
  return response.deleted_count;
};
