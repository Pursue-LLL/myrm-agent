import React from 'react';
import {
  ShieldCheck,
  RefreshCw,
  Send,
  RotateCcw,
  Sparkles,
  CheckCircle2,
  Lock,
} from 'lucide-react';
import { useGenUIAnswersReconciliationStore } from './useGenUIAnswersReconciliationStore';
import type { FormFieldSpec, FormFieldValue } from './genuiReconciliationTypes';

export const ReconciledDynamicFormCard: React.FC = () => {
  const {
    currentSpec,
    answers,
    dirtyFields,
    lastReconciliation,
    isSubmitted,
    updateFieldValue,
    simulateAgentSpecRefresh,
    submitForm,
    resetForm,
  } = useGenUIAnswersReconciliationStore();

  const handleFieldChange = (field: FormFieldSpec, rawVal: string | boolean | number) => {
    let parsedVal: FormFieldValue = rawVal;
    if (field.type === 'number') {
      const num = Number(rawVal);
      parsedVal = Number.isNaN(num) ? 0 : num;
    }
    updateFieldValue(field.fieldId, parsedVal);
  };

  const dirtyCount = Object.values(dirtyFields).filter(Boolean).length;

  return (
    <div className="w-full max-w-4xl mx-auto rounded-xl border border-slate-700/80 bg-slate-900/90 p-6 text-slate-100 shadow-xl backdrop-blur-md">
      {/* 头部元信息区 */}
      <div className="flex flex-col gap-3 pb-5 border-b border-slate-800 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-xs font-medium text-indigo-400 border border-indigo-500/20">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              GenUI Spec v{currentSpec.version}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400 border border-emerald-500/20">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              调和守卫保护中
            </span>
          </div>
          <h2 className="mt-2 text-xl font-bold tracking-tight text-white">
            {currentSpec.title}
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            {currentSpec.description}
          </p>
        </div>

        {/* 顶部模拟刷新按钮 */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              simulateAgentSpecRefresh();
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-indigo-500/30 bg-indigo-600/20 px-3.5 py-2 text-xs font-semibold text-indigo-300 hover:bg-indigo-600/30 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <RefreshCw className="w-4 h-4 text-indigo-400" />
            模拟 Agent 演进新规格
          </button>
        </div>
      </div>

      {/* 调和状态通知条 */}
      {lastReconciliation !== null && (
        <div className="my-4 flex items-center justify-between rounded-lg border border-teal-500/30 bg-teal-950/40 px-4 py-2.5 text-xs text-teal-200">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-teal-400 shrink-0" />
            <span>
              已完成状态调和：成功锁定并保护{' '}
              <strong className="text-teal-300">
                {lastReconciliation.preservedUserFieldsCount}
              </strong>{' '}
              项用户输入草稿，动态注入{' '}
              <strong className="text-teal-300">
                {lastReconciliation.initializedNewFieldsCount}
              </strong>{' '}
              项新版本缺省配置。
            </span>
          </div>
          <span className="text-slate-400 text-[10px]">
            {new Date(lastReconciliation.reconciledAt).toLocaleTimeString()}
          </span>
        </div>
      )}

      {/* 动态表单表体 */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submitForm();
        }}
        className="mt-6 space-y-5"
      >
        {currentSpec.fields.map((field) => {
          const val = answers[field.fieldId] ?? field.defaultValue;
          const isDirty = dirtyFields[field.fieldId] === true;

          return (
            <div
              key={field.fieldId}
              className={`rounded-lg border p-4 transition-all ${
                isDirty
                  ? 'border-indigo-500/40 bg-slate-800/70 shadow-sm'
                  : 'border-slate-800 bg-slate-800/30'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <label
                  htmlFor={`field-${field.fieldId}`}
                  className="block text-sm font-semibold text-slate-200"
                >
                  {field.label}
                  {field.required && (
                    <span className="ml-1 text-rose-400">*</span>
                  )}
                </label>
                {isDirty ? (
                  <span className="inline-flex items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-[11px] font-medium text-indigo-300">
                    <Lock className="w-3 h-3" />
                    用户已改动 (调和豁免)
                  </span>
                ) : (
                  <span className="text-[11px] text-slate-400">Spec 默认值</span>
                )}
              </div>

              {field.description && (
                <p className="text-xs text-slate-400 mb-2.5">
                  {field.description}
                </p>
              )}

              {/* 输入控件分支渲染 */}
              {field.type === 'text' && (
                <input
                  id={`field-${field.fieldId}`}
                  type="text"
                  value={String(val)}
                  onChange={(e) => {
                    handleFieldChange(field, e.target.value);
                  }}
                  className="w-full rounded-md border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              )}

              {field.type === 'number' && (
                <input
                  id={`field-${field.fieldId}`}
                  type="number"
                  value={Number(val)}
                  onChange={(e) => {
                    handleFieldChange(field, e.target.value);
                  }}
                  className="w-full rounded-md border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              )}

              {field.type === 'select' && (
                <select
                  id={`field-${field.fieldId}`}
                  value={String(val)}
                  onChange={(e) => {
                    handleFieldChange(field, e.target.value);
                  }}
                  className="w-full rounded-md border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  {(field.options ?? []).map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              )}

              {field.type === 'boolean' && (
                <label className="flex items-center gap-3 cursor-pointer pt-1">
                  <input
                    id={`field-${field.fieldId}`}
                    type="checkbox"
                    checked={Boolean(val)}
                    onChange={(e) => {
                      handleFieldChange(field, e.target.checked);
                    }}
                    className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-xs text-slate-300">
                    启用该配置项 (当前: {val ? '已开启' : '已禁用'})
                  </span>
                </label>
              )}
            </div>
          );
        })}

        {/* 底部操作区 */}
        <div className="flex flex-col gap-3 pt-4 border-t border-slate-800 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>总计 {currentSpec.fields.length} 个参数项</span>
            <span>•</span>
            <span>已修改 {dirtyCount} 项</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={resetForm}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700 active:scale-95 transition-all"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              恢复默认
            </button>
            <button
              type="submit"
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-md hover:bg-indigo-500 active:scale-95 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <Send className="w-3.5 h-3.5" />
              确认并提交审批
            </button>
          </div>
        </div>
      </form>

      {/* 提交成功提示 */}
      {isSubmitted && (
        <div className="mt-5 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-950/40 p-3 text-xs text-emerald-300">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>参数已安全提交并生成不可篡改审批流水。</span>
        </div>
      )}
    </div>
  );
};
