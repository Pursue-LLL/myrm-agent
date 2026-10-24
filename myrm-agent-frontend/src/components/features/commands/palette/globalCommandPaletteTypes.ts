/**
 * Data contracts for Global Fuzzy Command Palette & Status Bar Telemetry Suite.
 * Strict zero-any compliance aligned with Hermes Agent v0.21.0 & OpenHuman search hub parity.
 */

export type CommandActionCategory = 'model' | 'agent' | 'session' | 'system';

export interface CommandPaletteAction {
  id: string;
  title: string;
  description: string;
  category: CommandActionCategory;
  shortcut?: string;
  keyword: string;
}

export interface HistorySearchResultItem {
  chat_id: string;
  title: string;
  snippet: string;
  match_type: 'title' | 'content';
  timestamp_ms: number;
}

export interface TelemetryMetrics {
  cache_hit_rate: number; // e.g. 84.5%
  ttft_ms: number; // e.g. 240ms
  throughput_tokens_per_sec: number; // e.g. 142.5 tok/s
  estop_active: boolean;
}

export interface RotatingPlaceholderEntry {
  id: string;
  prompt: string;
  category: string;
}

export const DEFAULT_COMMAND_ACTIONS: readonly CommandPaletteAction[] = [
  {
    id: 'switch_model',
    title: 'Switch Active Model (/model)',
    description: 'Switch or configure active LLM provider (Claude, GPT, DeepSeek, Qwen)',
    category: 'model',
    shortcut: 'M',
    keyword: 'model llm gpt claude deepseek qwen provider',
  },
  {
    id: 'switch_agent',
    title: 'Switch Specialized Agent (/agent)',
    description: 'Switch persona to Code Architect, Test Runner, or Docs Specialist',
    category: 'agent',
    shortcut: 'A',
    keyword: 'agent profile persona architect bot',
  },
  {
    id: 'clear_context',
    title: 'Clear Current Context (/clear)',
    description: 'Flush conversation context and reset the context window',
    category: 'session',
    shortcut: 'C',
    keyword: 'clear reset flush context memory',
  },
  {
    id: 'export_session',
    title: 'Export Standalone HTML (/export)',
    description: 'Compile active chat session into offline interactive HTML package',
    category: 'session',
    shortcut: 'E',
    keyword: 'export share html download bundle',
  },
  {
    id: 'global_estop',
    title: 'Global Physical E-Stop (/estop)',
    description: 'Immediately abort all running agent swarms and active tools',
    category: 'system',
    shortcut: 'Esc',
    keyword: 'stop estop abort freeze cancel kill',
  },
] as const;
