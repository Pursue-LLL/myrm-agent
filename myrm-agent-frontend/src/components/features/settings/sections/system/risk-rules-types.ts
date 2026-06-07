export interface RiskRule {
  rule_id: string;
  display_name: string;
  description: string | null;
  pattern: string;
  severity: string;
  action: string;
  category: string;
  is_enabled: boolean;
  is_builtin: boolean;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface RiskHit {
  id: number;
  trace_id: string;
  session_id: string | null;
  user_id: string | null;
  rule_id: string;
  rule_name: string;
  severity: string;
  action: string;
  match_summary: string;
  created_at: string | null;
}

export const CATEGORY_MAP: Record<string, string> = {
  personal: 'categoryPersonal',
  company: 'categoryCompany',
  security: 'categorySecurity',
  finance_legal: 'categoryFinanceLegal',
  political: 'categoryPolitical',
  customer: 'categoryCustomer',
  custom: 'categoryCustom',
};

export const SEVERITY_COLORS: Record<string, string> = {
  low: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
  medium: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
  high: 'bg-red-500/10 text-red-600 dark:text-red-400',
};

export const ACTION_COLORS: Record<string, string> = {
  allow: 'bg-green-500/10 text-green-600 dark:text-green-400',
  block: 'bg-red-500/10 text-red-600 dark:text-red-400',
};
