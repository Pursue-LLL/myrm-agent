export type WorkMode = 'coding' | 'work';

export type WorkspaceThemeColor =
  | 'violet'
  | 'blue'
  | 'emerald'
  | 'amber'
  | 'rose'
  | 'indigo'
  | 'slate';

export type WorkspaceSemanticIcon =
  | 'code'
  | 'briefcase'
  | 'gamepad'
  | 'film'
  | 'database'
  | 'palette'
  | 'book'
  | 'terminal';

export interface WorkspaceVisualTheme {
  color: WorkspaceThemeColor;
  icon: WorkspaceSemanticIcon;
  customLabel?: string;
}

export interface WorkspaceItem {
  id: string;
  name: string;
  path: string;
  defaultMode: WorkMode;
  theme: WorkspaceVisualTheme;
  updatedAt: number;
}

export interface ModeAdaptiveSuggestion {
  id: string;
  title: string;
  mode: WorkMode;
  prompt: string;
  category: string;
}
