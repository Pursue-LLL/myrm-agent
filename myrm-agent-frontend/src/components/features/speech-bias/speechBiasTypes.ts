/**
 * 代码库上下文感知语音输入智能纠偏与工程术语偏置类型定义
 */

export type DevTermCategory =
  | 'cli_tool'
  | 'framework'
  | 'package'
  | 'git_branch'
  | 'ast_symbol'
  | 'skill'
  | 'custom';

export interface DevTermItem {
  id: string;
  term: string;
  category: DevTermCategory;
  aliases: string[];
  weight: number;
  source?: string;
}

export interface CorrectionRecord {
  id: string;
  original: string;
  corrected: string;
  category: DevTermCategory;
  confidence: number;
  startIndex: number;
  endIndex: number;
}

export interface CorrectionResult {
  originalText: string;
  correctedText: string;
  corrections: CorrectionRecord[];
  containsCodeBlocks: boolean;
}

export type DictationStatus = 'idle' | 'listening' | 'correcting' | 'ready' | 'error';

export interface SpeechBiasState {
  status: DictationStatus;
  rawTranscript: string;
  correctedTranscript: string;
  activeCorrections: CorrectionRecord[];
  lexicon: DevTermItem[];
  isAutoCorrectEnabled: boolean;
  isDrawerOpen: boolean;
  activeBranchName: string;
  recentAstSymbols: string[];
  installedSkills: string[];
  lastError: string | null;
}
