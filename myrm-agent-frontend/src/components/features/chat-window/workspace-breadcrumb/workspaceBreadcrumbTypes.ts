/**
 * [INPUT]
 * - None (Pure domain type definitions for Workspace Breadcrumb Path & Desktop Reveal)
 *
 * [OUTPUT]
 * - PathSegment, WorkspaceLocationInfo, WorkspaceRevealAction,
 *   WorkspaceRevealEventPayload, WorkspaceBreadcrumbStoreState
 *
 * [POS]
 * Unified types for Item 197 (P1): WorkspaceBreadcrumbPathAndDesktopRevealSuite.
 * Resolves artifact landing anxiety by visualizing physical project paths,
 * supporting Finder/Explorer reveals, path copying, and terminal bridging.
 */

export interface PathSegment {
  readonly name: string;
  readonly fullPath: string;
  readonly isRoot: boolean;
  readonly isLeaf: boolean;
}

export type PlatformKind = 'darwin' | 'win32' | 'linux';

export interface WorkspaceLocationInfo {
  readonly rawPath: string;
  readonly normalizedPath: string;
  readonly segments: readonly PathSegment[];
  readonly platform: PlatformKind;
  readonly isSandbox: boolean;
}

export type WorkspaceRevealAction = 'finder' | 'terminal' | 'copy_path';

export interface WorkspaceRevealEventPayload {
  readonly action: WorkspaceRevealAction;
  readonly path: string;
  readonly timestamp: number;
}

export interface WorkspaceBreadcrumbStoreState {
  readonly workspacePathByChatId: Readonly<Record<string, string>>;
  readonly activeChatId: string | null;
  readonly defaultPath: string;
  readonly lastRevealedAction: WorkspaceRevealAction | null;
  readonly isCopied: boolean;
}
