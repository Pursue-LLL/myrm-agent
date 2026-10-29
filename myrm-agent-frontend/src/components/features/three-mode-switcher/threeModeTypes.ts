/**
 * 面向非程序员知识工作者的「Ask 问一问 / Plan 想一想 / Craft 做一做」三态心智化模式类型定义
 */

export type OfficeWorkspaceMode = 'ask' | 'plan' | 'craft';

export interface ModeSecurityPolicy {
  readOnly: boolean;
  requirePlanApproval: boolean;
  allowFileWrites: boolean;
  allowShellExecution: boolean;
  bypassConfirmations: boolean;
}

export interface OfficeModeMetadata {
  id: OfficeWorkspaceMode;
  title: string;
  subTitle: string;
  tagline: string;
  description: string;
  policy: ModeSecurityPolicy;
  recommendedFor: string;
  shortcut: string;
  badgeBg: string;
  badgeText: string;
  badgeBorder: string;
}

export interface WriteIntentDetectionResult {
  hasWriteIntent: boolean;
  matchedKeywords: string[];
  suggestedMode: OfficeWorkspaceMode;
  guidanceMessage: string;
}
