'use client';

/**
 * Step 1 component for SolidifyToSkillWizardModal: Parameter Minimization.
 */

import React from 'react';
import { ParameterExtractionRule } from './solidifyTypes';

interface SolidifyStepParamsProps {
  skillName: string;
  setSkillName: (val: string) => void;
  displayTitle: string;
  setDisplayTitle: (val: string) => void;
  description: string;
  setDescription: (val: string) => void;
  parameters: ParameterExtractionRule[];
  setParameters: (params: ParameterExtractionRule[]) => void;
  paramHelpText: string;
  nameLabel: string;
  displayTitleLabel: string;
  descriptionLabel: string;
}

export const SolidifyStepParams: React.FC<SolidifyStepParamsProps> = ({
  skillName,
  setSkillName,
  displayTitle,
  setDisplayTitle,
  description,
  setDescription,
  parameters,
  setParameters,
  paramHelpText,
  nameLabel,
  displayTitleLabel,
  descriptionLabel,
}) => {
  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-xl bg-indigo-950/20 border border-indigo-900/30 text-xs text-slate-300">
        <span className="font-semibold text-indigo-300 block mb-1">
          {paramHelpText}
        </span>
        系统已自动锁定骨架结构，仅提取每次生成必须变动的动态入参。
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
        <div>
          <label htmlFor="skill-name-input" className="text-xs font-medium text-slate-400 block mb-1">
            {nameLabel}
          </label>
          <input
            id="skill-name-input"
            type="text"
            value={skillName}
            onChange={(e) => {
              setSkillName(e.target.value);
            }}
            className="w-full px-3 py-2 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
          />
        </div>
        <div>
          <label htmlFor="display-title-input" className="text-xs font-medium text-slate-400 block mb-1">
            {displayTitleLabel}
          </label>
          <input
            id="display-title-input"
            type="text"
            value={displayTitle}
            onChange={(e) => {
              setDisplayTitle(e.target.value);
            }}
            className="w-full px-3 py-2 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      <div>
        <label htmlFor="description-input" className="text-xs font-medium text-slate-400 block mb-1">
          {descriptionLabel}
        </label>
        <textarea
          id="description-input"
          rows={2}
          value={description}
          onChange={(e) => {
            setDescription(e.target.value);
          }}
          className="w-full px-3 py-2 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 resize-none"
        />
      </div>

      {/* Dynamic Parameter Cards */}
      <div className="space-y-2">
        <span className="text-xs font-semibold text-slate-300">
          动态插值槽位 ({parameters.length})
        </span>
        <div className="space-y-2">
          {parameters.map((p, idx) => (
            <div
              key={p.name}
              className="flex items-center justify-between p-3 rounded-xl bg-slate-950/40 border border-slate-800 text-xs"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded">
                  {p.placeholderPattern}
                </span>
                <input
                  type="text"
                  aria-label={`Description for ${p.name}`}
                  value={p.description}
                  onChange={(e) => {
                    const updated = [...parameters];
                    updated[idx].description = e.target.value;
                    setParameters(updated);
                  }}
                  className="bg-transparent text-slate-300 border-none focus:outline-none text-xs"
                />
              </div>
              <span className="text-[10px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">
                必填
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
