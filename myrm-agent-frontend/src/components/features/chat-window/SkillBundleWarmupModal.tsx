'use client';

import React, { useState } from 'react';
import {
  Boxes,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  X,
  ChevronDown,
  ChevronUp,
  PackageCheck,
  Power,
  RotateCcw,
} from 'lucide-react';

export type WarmupStatus = 'ready' | 'warning' | 'blocked';
export type BundleCategory = 'coding' | 'writing' | 'marketing' | 'finance' | 'security' | 'custom';

export interface BundleSkillData {
  skill_id: string;
  name: string;
  description: string;
  required_env_vars: string[];
  required_tools: string[];
  is_optional: boolean;
}

export interface SkillBundleData {
  bundle_id: string;
  name: string;
  description: string;
  category: BundleCategory;
  skills: BundleSkillData[];
  author: string;
  version: string;
  tags: string[];
}

export interface SkillBundleWarmupModalProps {
  chatId: string;
  bundles?: SkillBundleData[];
  activeBundleIds?: string[];
  onActivateBundle?: (bundleId: string, force: boolean) => Promise<void> | void;
  onDeactivateBundle?: (bundleId: string) => Promise<void> | void;
  onDismiss: () => void;
  className?: string;
}

const DEFAULT_BUNDLES: SkillBundleData[] = [
  {
    bundle_id: 'bundle_fullstack_coding',
    name: 'Full-Stack Code Engineering',
    description: 'End-to-end coding bundle with refactoring, test execution, and static linting.',
    category: 'coding',
    skills: [
      { skill_id: 'code-refactor', name: 'Code Refactor', description: 'Analyzes code smell and applies clean refactoring.', required_env_vars: [], required_tools: [], is_optional: false },
      { skill_id: 'test-runner', name: 'Test Execution Suite', description: 'Runs unit tests and asserts coverage.', required_env_vars: [], required_tools: [], is_optional: false },
      { skill_id: 'security-linter', name: 'Security Linter', description: 'Scans for secret leakage and CWE vulnerabilities.', required_env_vars: [], required_tools: [], is_optional: true },
    ],
    author: 'system',
    version: '1.0.0',
    tags: ['coding', 'refactor', 'pytest'],
  },
  {
    bundle_id: 'bundle_wechat_publisher',
    name: 'Official Account Content Creation',
    description: 'Integrated publishing suite for headline generation, copywriting, and AB testing.',
    category: 'writing',
    skills: [
      { skill_id: 'content-topic-generator', name: 'Topic Generator', description: 'Brainstorms viral topics from trends.', required_env_vars: [], required_tools: [], is_optional: false },
      { skill_id: 'wechat-publisher', name: 'WeChat Article Publisher', description: 'Formats and publishes articles.', required_env_vars: ['WECHAT_APP_SECRET'], required_tools: [], is_optional: false },
      { skill_id: 'title-ab-tester', name: 'Headline A/B Tester', description: 'Simulates reader clickthrough rates.', required_env_vars: [], required_tools: [], is_optional: true },
    ],
    author: 'system',
    version: '1.0.0',
    tags: ['wechat', 'publishing', 'copywriting'],
  },
  {
    bundle_id: 'bundle_finance_audit',
    name: 'Financial Cleaning & Reconciliation',
    description: 'Multi-table reconciliation, spreadsheet normalization, and invoice verification.',
    category: 'finance',
    skills: [
      { skill_id: 'excel-cleaner', name: 'Excel Normalizer', description: 'Normalizes malformed tabular data.', required_env_vars: [], required_tools: [], is_optional: false },
      { skill_id: 'invoice-matcher', name: 'Invoice Reconciliation', description: 'Cross-checks ledger against invoice records.', required_env_vars: [], required_tools: [], is_optional: false },
    ],
    author: 'system',
    version: '1.0.0',
    tags: ['finance', 'excel', 'reconciliation'],
  },
];

export const SkillBundleWarmupModal: React.FC<SkillBundleWarmupModalProps> = ({
  chatId,
  bundles = DEFAULT_BUNDLES,
  activeBundleIds = [],
  onActivateBundle,
  onDeactivateBundle,
  onDismiss,
  className = '',
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [expandedBundleIds, setExpandedBundleIds] = useState<Record<string, boolean>>({});
  const [forceMap, setForceMap] = useState<Record<string, boolean>>({});
  const [loadingMap, setLoadingMap] = useState<Record<string, boolean>>({});

  const toggleExpand = (bundleId: string) => {
    setExpandedBundleIds((prev) => ({ ...prev, [bundleId]: !prev[bundleId] }));
  };

  const handleToggleActivation = async (bundle: SkillBundleData) => {
    const isActive = activeBundleIds.includes(bundle.bundle_id);
    setLoadingMap((prev) => ({ ...prev, [bundle.bundle_id]: true }));
    try {
      if (isActive && onDeactivateBundle) {
        await onDeactivateBundle(bundle.bundle_id);
      } else if (!isActive && onActivateBundle) {
        const force = forceMap[bundle.bundle_id] ?? false;
        await onActivateBundle(bundle.bundle_id, force);
      }
    } finally {
      setLoadingMap((prev) => ({ ...prev, [bundle.bundle_id]: false }));
    }
  };

  const filteredBundles = selectedCategory === 'all'
    ? bundles
    : bundles.filter((b) => b.category === selectedCategory);

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in ${className}`}
      data-testid="skill-bundle-warmup-modal"
    >
      <div className="bg-card border border-border/80 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden text-xs">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/60 bg-muted/30">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Boxes className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-semibold text-sm text-foreground flex items-center gap-2">
                Scenario Skill Bundles & Warmup Manager
                <span className="px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 text-[10px] font-mono border border-indigo-500/20">
                  {bundles.length} available
                </span>
              </h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Atomic scenario packaging, dependency pre-flight checks, and session mounting for chat: {chatId}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onDismiss}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Close"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Category Filter Chips */}
        <div className="flex items-center gap-1.5 px-5 py-2.5 border-b border-border/40 overflow-x-auto bg-background/50">
          {['all', 'coding', 'writing', 'finance', 'security'].map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => {
                setSelectedCategory(cat);
              }}
              className={`px-3 py-1 rounded-full text-[11px] font-medium capitalize transition-colors ${
                selectedCategory === cat
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Bundles List */}
        <div className="p-5 overflow-y-auto space-y-3 flex-1">
          {filteredBundles.map((bundle) => {
            const isActive = activeBundleIds.includes(bundle.bundle_id);
            const isExpanded = expandedBundleIds[bundle.bundle_id] ?? false;
            const isLoading = loadingMap[bundle.bundle_id] ?? false;
            const isForce = forceMap[bundle.bundle_id] ?? false;
            const hasRequiredEnv = bundle.skills.some((s) => s.required_env_vars.length > 0);

            return (
              <div
                key={bundle.bundle_id}
                className={`border rounded-xl p-3.5 transition-all ${
                  isActive
                    ? 'border-emerald-500/40 bg-emerald-500/5 shadow-sm'
                    : 'border-border/60 bg-muted/20 hover:border-border'
                }`}
                data-testid={`bundle-card-${bundle.bundle_id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground text-xs">{bundle.name}</span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-mono font-medium bg-muted text-muted-foreground">
                        {bundle.category}
                      </span>
                      <span className="text-[10px] text-muted-foreground font-mono">v{bundle.version}</span>
                      {isActive && (
                        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-medium">
                          <CheckCircle2 className="w-3 h-3" /> Active
                        </span>
                      )}
                    </div>
                    <p className="text-muted-foreground text-[11px] mt-1">{bundle.description}</p>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      disabled={isLoading}
                      onClick={() => {
                        void handleToggleActivation(bundle);
                      }}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-colors text-[11px] ${
                        isActive
                          ? 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30'
                          : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm'
                      }`}
                    >
                      {isLoading ? (
                        <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                      ) : isActive ? (
                        <>
                          <Power className="w-3 h-3" /> Deactivate
                        </>
                      ) : (
                        <>
                          <PackageCheck className="w-3.5 h-3.5" /> 1-Click Activate
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        toggleExpand(bundle.bundle_id);
                      }}
                      className="p-1 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors"
                      title={isExpanded ? 'Collapse' : 'Expand'}
                      aria-label={isExpanded ? 'Collapse' : 'Expand'}
                    >
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Force Option when bundle requires env vars */}
                {!isActive && hasRequiredEnv && (
                  <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1 text-amber-400">
                      <AlertTriangle className="w-3 h-3" /> Pre-flight requires environment variables
                    </span>
                    <label className="flex items-center gap-1.5 cursor-pointer hover:text-foreground">
                      <input
                        type="checkbox"
                        checked={isForce}
                        onChange={(e) => {
                          setForceMap((prev) => ({ ...prev, [bundle.bundle_id]: e.target.checked }));
                        }}
                        className="rounded border-border text-emerald-500 focus:ring-emerald-400"
                      />
                      <span>Force Mount (Bypass Warmup Block)</span>
                    </label>
                  </div>
                )}

                {/* Expanded Skills Specification List */}
                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-border/50 space-y-2">
                    <p className="font-medium text-foreground text-[11px]">
                      Packaged Skills ({bundle.skills.length}):
                    </p>
                    <div className="space-y-1.5">
                      {bundle.skills.map((skill) => (
                        <div
                          key={skill.skill_id}
                          className="p-2 rounded bg-background/60 border border-border/40 flex items-start justify-between gap-2"
                        >
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono text-primary font-medium">{skill.skill_id}</span>
                              <span className="text-foreground font-medium">({skill.name})</span>
                              {skill.is_optional && (
                                <span className="text-[10px] text-muted-foreground italic">(optional)</span>
                              )}
                            </div>
                            <p className="text-muted-foreground text-[10px] mt-0.5">{skill.description}</p>
                          </div>
                          {skill.required_env_vars.length > 0 && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] font-mono shrink-0">
                              env: {skill.required_env_vars.join(', ')}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default SkillBundleWarmupModal;
