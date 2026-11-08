'use client';

/**
 * [INPUT] ./useWikiImport::WikiImportController (POS: 对话框开关与回调), ../wiki (POS: 导入冲突 / 安全提示 / 链接 / 视频对话框)
 * [OUTPUT] WikiImportDialogs: 四个导入对话框: 路径冲突 (保留跳过 / 覆盖重试)、安全拦截与脱敏提示、链接导入、视频导入
 * [POS] Wiki 面板底部的导入对话框挂载点; 开关与回调都由 useWikiImport 提供。
 */

import { WikiImportConflictDialog } from '../wiki/WikiImportConflictDialog';
import { WikiImportSecurityDialog } from '../wiki/WikiImportSecurityDialog';
import { WikiUrlImportDialog } from '../wiki/WikiUrlImportDialog';
import { WikiVideoImportDialog } from '../wiki/WikiVideoImportDialog';
import type { WikiImportController } from './useWikiImport';

interface WikiImportDialogsProps {
  agentScopeId: string | null;
  imports: Pick<
    WikiImportController,
    | 'importConflictOpen'
    | 'importConflictPaths'
    | 'dismissImportConflict'
    | 'keepSkippedImports'
    | 'retryImportWithSupersede'
    | 'importSecurityOpen'
    | 'importSecurityBlockedPaths'
    | 'importSecurityRedactedPaths'
    | 'dismissImportSecurity'
    | 'urlImportDialogOpen'
    | 'setUrlImportDialogOpen'
    | 'handleUrlImportFinished'
    | 'videoImportDialogOpen'
    | 'setVideoImportDialogOpen'
    | 'handleVideoImportFinished'
  >;
}

export function WikiImportDialogs({ agentScopeId, imports }: WikiImportDialogsProps) {
  return (
    <>
      <WikiImportConflictDialog
        open={imports.importConflictOpen}
        conflictPaths={imports.importConflictPaths}
        onClose={imports.dismissImportConflict}
        onKeepSkipped={imports.keepSkippedImports}
        onSupersede={imports.retryImportWithSupersede}
      />
      <WikiImportSecurityDialog
        open={imports.importSecurityOpen}
        blockedPaths={imports.importSecurityBlockedPaths}
        redactedPaths={imports.importSecurityRedactedPaths}
        onClose={imports.dismissImportSecurity}
      />
      <WikiUrlImportDialog
        open={imports.urlImportDialogOpen}
        onOpenChange={imports.setUrlImportDialogOpen}
        agentScopeId={agentScopeId}
        onImportFinished={imports.handleUrlImportFinished}
      />
      <WikiVideoImportDialog
        open={imports.videoImportDialogOpen}
        onOpenChange={imports.setVideoImportDialogOpen}
        agentScopeId={agentScopeId}
        onImportFinished={imports.handleVideoImportFinished}
      />
    </>
  );
}
