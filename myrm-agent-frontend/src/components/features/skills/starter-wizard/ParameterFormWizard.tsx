import React from 'react';
import { Sliders, Calendar, Compass } from 'lucide-react';
import type { ParameterSchema } from './starterWizardTypes';

interface ParameterFormWizardProps {
  parameters: ParameterSchema[];
  formValues: Record<string, string>;
  onFormValueChange: (key: string, value: string) => void;
}

export const ParameterFormWizard: React.FC<ParameterFormWizardProps> = ({
  parameters,
  formValues,
  onFormValueChange,
}) => {
  // 过滤掉已经在嗅探器中选择的参数
  const normalParameters = parameters.filter((p) => p.type !== 'sniffer_select');

  if (normalParameters.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-700/60 bg-slate-900/60 p-3.5 backdrop-blur-sm">
      <div className="flex items-center space-x-1.5 border-b border-slate-800 pb-2">
        <Sliders className="h-4 w-4 text-sky-400" />
        <span className="text-xs font-semibold text-slate-200">场景精炼参数配置</span>
        <span className="text-[11px] text-slate-400">（选定最适合您的提炼视角）</span>
      </div>

      <div className="space-y-3.5">
        {normalParameters.map((param) => {
          const currentValue = formValues[param.key] ?? param.defaultValue ?? '';
          const isTimeWindow = param.type === 'time_window';

          return (
            <div key={param.key} className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <label htmlFor={`param-${param.key}`} className="flex items-center space-x-1 font-medium text-slate-300">
                  {isTimeWindow ? (
                    <Calendar className="h-3.5 w-3.5 text-blue-400" />
                  ) : (
                    <Compass className="h-3.5 w-3.5 text-purple-400" />
                  )}
                  <span>{param.label}</span>
                  {param.required && <span className="text-rose-400">*</span>}
                </label>
                <span className="text-[10px] text-slate-400">{param.description}</span>
              </div>

              {param.options && param.options.length <= 4 ? (
                <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-2">
                  {param.options.map((option) => {
                    const isSelected = currentValue === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => {
                          onFormValueChange(param.key, option.value);
                        }}
                        className={`rounded-md border px-2.5 py-1.5 text-left text-xs transition-colors ${
                          isSelected
                            ? 'border-blue-500 bg-blue-500/15 text-blue-200 font-medium'
                            : 'border-slate-700/80 bg-slate-800/60 text-slate-400 hover:border-slate-600 hover:text-slate-300'
                        }`}
                      >
                        <div>{option.label}</div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <select
                  id={`param-${param.key}`}
                  value={currentValue}
                  onChange={(e) => {
                    onFormValueChange(param.key, e.target.value);
                  }}
                  className="w-full rounded-md border border-slate-700 bg-slate-800/90 px-3 py-1.5 text-xs text-slate-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  {param.options?.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
