'use client';

/**
 * Step 2 component for SolidifyToSkillWizardModal: 4-in-1 Asset Bundle Preview.
 */

import React from 'react';
import { FileCode, FileText, FolderGit2, Workflow } from 'lucide-react';

interface SolidifyStepBundleProps {
  planHint: boolean;
  setPlanHint: (val: boolean) => void;
  planHintLabel: string;
}

export const SolidifyStepBundle: React.FC<SolidifyStepBundleProps> = ({
  planHint,
  setPlanHint,
  planHintLabel,
}) => {
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-3">
        <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
          <FolderGit2 className="w-4 h-4 text-indigo-400" />
          四位一体标准全包目录结构
        </span>
        <div className="space-y-1.5 text-xs font-mono text-slate-400 pl-2 border-l border-slate-800">
          <div className="flex items-center gap-2 text-slate-200">
            <FileText className="w-3.5 h-3.5 text-sky-400" />
            <span>SKILL.md</span>
            <span className="text-[11px] text-slate-500 font-sans">
              (YAML Frontmatter + 参数最小化使用规范)
            </span>
          </div>
          <div className="flex items-center gap-2 text-slate-200">
            <FileCode className="w-3.5 h-3.5 text-amber-400" />
            <span>assets/template.html</span>
            <span className="text-[11px] text-slate-500 font-sans">
              (锁定样式骨架与插值占位符)
            </span>
          </div>
          <div className="flex items-center gap-2 text-slate-200">
            <FileCode className="w-3.5 h-3.5 text-emerald-400" />
            <span>assets/example.html</span>
            <span className="text-[11px] text-slate-500 font-sans">
              (本次打磨成型的真机样例产物)
            </span>
          </div>
          <div className="flex items-center gap-2 text-slate-200">
            <FileText className="w-3.5 h-3.5 text-purple-400" />
            <span>references/design_guidelines.md</span>
            <span className="text-[11px] text-slate-500 font-sans">
              (断点响应与无裂图矢量规约)
            </span>
          </div>
        </div>
      </div>

      {/* Plan Before Execute Option */}
      <div className="flex items-center justify-between p-3.5 rounded-xl bg-slate-950/40 border border-slate-800">
        <div className="flex items-center gap-2">
          <Workflow className="w-4 h-4 text-indigo-400" />
          <span className="text-xs text-slate-300">{planHintLabel}</span>
        </div>
        <input
          type="checkbox"
          aria-label="Enforce plan before execute hint"
          checked={planHint}
          onChange={(e) => {
            setPlanHint(e.target.checked);
          }}
          className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 bg-slate-900 border-slate-700"
        />
      </div>
    </div>
  );
};
