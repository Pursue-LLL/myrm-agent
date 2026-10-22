import React from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  RefreshCw,
  Server,
  ShieldCheck,
  Stethoscope,
  Wand2,
  Wifi,
} from 'lucide-react';
import { useProgressiveOnboardingStore } from './useProgressiveOnboardingStore';
import type { DoctorProbeResult } from './progressiveOnboardingTypes';

interface SelfHealingDoctorProps {
  className?: string;
}

export const SelfHealingDoctor: React.FC<SelfHealingDoctorProps> = ({
  className = '',
}) => {
  const {
    doctorProbes,
    isDoctorScanning,
    runDoctorScan,
    fixDoctorProbe,
  } = useProgressiveOnboardingStore();

  const renderStatusIcon = (status: DoctorProbeResult['status']): React.ReactElement => {
    switch (status) {
      case 'ok':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />;
      case 'warning':
        return <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />;
      default:
        return <CheckCircle2 className="w-4 h-4 text-slate-400 shrink-0" />;
    }
  };

  return (
    <section
      aria-label="一键自愈健康诊断探针"
      className={`rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow-sm backdrop-blur ${className}`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-teal-500/10 text-teal-400 border border-teal-500/20">
            <Stethoscope className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">一键自愈诊断探针 (Self-Healing Doctor)</h3>
            <p className="text-[11px] text-slate-400">
              就绪自诊断 · 沙箱/端口/本地模型连通性自动排查与一键自愈
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            runDoctorScan();
          }}
          disabled={isDoctorScanning}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:text-white transition-colors disabled:opacity-50"
          aria-label="重新运行诊断探针"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isDoctorScanning ? 'animate-spin' : ''}`} />
          <span>{isDoctorScanning ? '深度诊断中...' : '重新自检'}</span>
        </button>
      </div>

      {/* 探针列表 */}
      <div className="mt-3 space-y-2">
        {doctorProbes.map((probe) => (
          <div
            key={probe.id}
            className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              {renderStatusIcon(probe.status)}
              <div className="min-w-0">
                <div className="font-medium text-slate-200">{probe.name}</div>
                <div className="text-[11px] text-slate-400 truncate">{probe.message}</div>
              </div>
            </div>

            {probe.status !== 'ok' && probe.fixActionText && (
              <button
                type="button"
                onClick={() => {
                  fixDoctorProbe(probe.id);
                }}
                className="flex items-center gap-1 rounded bg-teal-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-teal-500 shrink-0 transition-colors shadow-sm"
                aria-label={`自愈修复 ${probe.name}`}
              >
                <Wand2 className="w-3 h-3" />
                <span>{probe.fixActionText}</span>
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
};
