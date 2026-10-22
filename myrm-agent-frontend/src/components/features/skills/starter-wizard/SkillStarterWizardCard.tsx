import React from 'react';
import { X, Sparkles, CheckCheck } from 'lucide-react';
import { useSkillStarterWizardStore } from './useSkillStarterWizardStore';
import { LocalResourceSnifferDropdown } from './LocalResourceSnifferDropdown';
import { ParameterFormWizard } from './ParameterFormWizard';
import { OneClickTrialRunPanel } from './OneClickTrialRunPanel';
import { OneClickRoutineSchedulerCard } from './OneClickRoutineSchedulerCard';

export const SkillStarterWizardCard: React.FC = () => {
  const {
    isOpen,
    activeSkill,
    formValues,
    sniffedResources,
    isSniffing,
    selectedResourceId,
    trialRun,
    cronBlueprint,
    closeWizard,
    setFormValue,
    selectResource,
    refreshSniffer,
    executeTrialRun,
    toggleCronHosting,
    updateTargetChannel,
  } = useSkillStarterWizardStore();

  if (!isOpen || !activeSkill) {
    return null;
  }

  const snifferParam = activeSkill.parameters.find((p) => p.type === 'sniffer_select');

  return (
    <section
      aria-label="技能安装后即刻体验向导卡"
      className="relative my-4 w-full rounded-xl border border-blue-500/30 bg-slate-900/95 p-4 shadow-xl backdrop-blur-md transition-all"
    >
      <div className="flex items-start justify-between border-b border-slate-800 pb-3">
        <div className="flex items-start space-x-2.5">
          <div className="rounded-lg bg-blue-500/10 p-2 text-blue-400">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-semibold text-slate-100">{activeSkill.skillName}</h3>
              <span className="rounded-full bg-blue-500/20 px-2 py-0.5 text-[10px] font-medium text-blue-300">
                {activeSkill.category}
              </span>
              <span className="inline-flex items-center space-x-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                <CheckCheck className="h-3 w-3" />
                <span>安装就绪</span>
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">{activeSkill.description}</p>
          </div>
        </div>

        <button
          type="button"
          onClick={closeWizard}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          aria-label="关闭向导卡"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-4 space-y-3.5">
        {snifferParam && (
          <LocalResourceSnifferDropdown
            label={snifferParam.label}
            description={snifferParam.description}
            resources={sniffedResources}
            selectedResourceId={selectedResourceId}
            isSniffing={isSniffing}
            onSelectResource={selectResource}
            onRefresh={() => {
              void refreshSniffer();
            }}
          />
        )}

        <ParameterFormWizard
          parameters={activeSkill.parameters}
          formValues={formValues}
          onFormValueChange={setFormValue}
        />

        <OneClickTrialRunPanel
          trialRun={trialRun}
          onExecuteTrialRun={() => {
            void executeTrialRun();
          }}
        />

        <OneClickRoutineSchedulerCard
          cronBlueprint={cronBlueprint}
          onToggleCronHosting={(enable) => {
            void toggleCronHosting(enable);
          }}
          onUpdateChannel={updateTargetChannel}
        />
      </div>

      <div className="mt-3.5 flex items-center justify-between border-t border-slate-800/80 pt-2.5 text-[11px] text-slate-400">
        <span>配置已原地生效，随时可在会话中下发自然语言指令或等待定时推送</span>
        <button
          type="button"
          onClick={closeWizard}
          className="rounded px-2.5 py-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          完成并收起
        </button>
      </div>
    </section>
  );
};
