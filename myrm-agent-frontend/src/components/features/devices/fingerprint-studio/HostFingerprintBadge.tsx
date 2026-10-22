'use client';

import React, { useState } from 'react';
import {
  Laptop,
  Server,
  Cpu,
  Activity,
  Layers,
  CheckCircle2,
  AlertCircle,
  Clock,
  Wifi,
} from 'lucide-react';
import { HostDevice } from './fingerprintStudioTypes';
import { formatHardwareBadge, computeDeviceHealth } from './deviceFingerprintEngine';
import { useFingerprintStudioStore } from './useFingerprintStudioStore';

interface HostFingerprintBadgeProps {
  device: HostDevice;
  mode?: 'mini' | 'expanded';
  showSwitchAction?: boolean;
}

export const HostFingerprintBadge: React.FC<HostFingerprintBadgeProps> = ({
  device,
  mode = 'mini',
  showSwitchAction = false,
}) => {
  const [showPopover, setShowPopover] = useState(false);
  const activeDeviceId = useFingerprintStudioStore((s) => s.activeDeviceId);
  const setActiveDevice = useFingerprintStudioStore((s) => s.setActiveDevice);

  const isActive = activeDeviceId === device.hardware.deviceId;
  const badgeInfo = formatHardwareBadge(device.hardware);
  const health = computeDeviceHealth(device.telemetry);

  const getPlatformIcon = () => {
    if (device.hardware.kind === 'cloud_pod') {
      return <Layers className="w-3.5 h-3.5 text-sky-400" aria-label="Cloud Pod" />;
    }
    if (device.hardware.kind === 'remote_server') {
      return <Server className="w-3.5 h-3.5 text-purple-400" aria-label="Remote Server" />;
    }
    if (device.hardware.platform === 'macos') {
      return <Laptop className="w-3.5 h-3.5 text-slate-300" aria-label="macOS Device" />;
    }
    return <Cpu className="w-3.5 h-3.5 text-emerald-400" aria-label="Windows/Linux Device" />;
  };

  const getStatusIndicator = () => {
    if (health.status === 'offline') {
      return <div className="w-2 h-2 rounded-full bg-slate-500" title="离线" />;
    }
    if (health.isCongested) {
      return <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" title="高负载排队" />;
    }
    if (health.status === 'busy') {
      return <div className="w-2 h-2 rounded-full bg-blue-500" title="执行中" />;
    }
    return <div className="w-2 h-2 rounded-full bg-emerald-500" title="就绪" />;
  };

  return (
    <div
      className="relative inline-block font-sans text-xs select-none"
      onMouseEnter={() => { setShowPopover(true); }}
      onMouseLeave={() => { setShowPopover(false); }}
    >
      <div
        className={`flex items-center gap-1.5 px-2 py-1 rounded-md border transition-colors ${
          isActive
            ? 'bg-blue-500/10 border-blue-500/40 text-blue-200 shadow-sm'
            : 'bg-slate-900/60 border-slate-700/60 text-slate-300 hover:border-slate-500/60'
        }`}
      >
        {getPlatformIcon()}
        {getStatusIndicator()}

        <span className="font-semibold text-slate-200">
          {device.hardware.hostName}
        </span>

        <span className="px-1 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">
          {device.hardware.chipModel.split(' ')[0]}
        </span>

        {device.hardware.gpuModel && (
          <span className="px-1 py-0.5 rounded text-[10px] bg-emerald-950/60 text-emerald-300 border border-emerald-700/50">
            RTX
          </span>
        )}

        {mode === 'expanded' && (
          <span className="text-[11px] text-slate-400 ml-1">
            {health.loadScore}% 负荷
          </span>
        )}
      </div>

      {showPopover && (
        <div className="absolute left-0 top-full mt-1.5 z-50 w-64 p-3 rounded-lg bg-slate-900 border border-slate-700/80 shadow-2xl backdrop-blur-md text-slate-200">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div>
              <div className="font-semibold text-sm text-slate-100 flex items-center gap-1.5">
                {badgeInfo.title}
                {isActive && (
                  <span className="text-[10px] px-1 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                    当前执行端
                  </span>
                )}
              </div>
              <div className="text-[11px] text-slate-400">{badgeInfo.subtitle}</div>
            </div>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
              {badgeInfo.tag}
            </span>
          </div>

          <div className="mt-2.5 space-y-1.5 text-[11px]">
            <div className="flex justify-between items-center text-slate-400">
              <span className="flex items-center gap-1">
                <Activity className="w-3 h-3 text-slate-400" /> CPU 负载
              </span>
              <span className="font-mono text-slate-200">{device.telemetry.cpuUsagePct}%</span>
            </div>

            <div className="flex justify-between items-center text-slate-400">
              <span className="flex items-center gap-1">
                <Cpu className="w-3 h-3 text-slate-400" /> 内存占用
              </span>
              <span className="font-mono text-slate-200">{device.telemetry.memoryUsagePct}%</span>
            </div>

            {device.telemetry.gpuUsagePct !== undefined && (
              <div className="flex justify-between items-center text-slate-400">
                <span className="flex items-center gap-1">
                  <Activity className="w-3 h-3 text-emerald-400" /> GPU 算力
                </span>
                <span className="font-mono text-emerald-300">{device.telemetry.gpuUsagePct}%</span>
              </div>
            )}

            <div className="flex justify-between items-center text-slate-400">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3 text-slate-400" /> 进行中任务
              </span>
              <span className="font-mono text-slate-200">{device.telemetry.activeTasksCount}</span>
            </div>

            <div className="flex justify-between items-center text-slate-400">
              <span className="flex items-center gap-1">
                <Wifi className="w-3 h-3 text-slate-400" /> 延迟
              </span>
              <span className="font-mono text-slate-200">{device.telemetry.latencyMs} ms</span>
            </div>
          </div>

          {showSwitchAction && !isActive && (
            <button
              type="button"
              onClick={() => {
                setActiveDevice(device.hardware.deviceId);
                setShowPopover(false);
              }}
              className="mt-3 w-full py-1 px-2 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium flex items-center justify-center gap-1 transition-colors"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              设为默认调度主机
            </button>
          )}
        </div>
      )}
    </div>
  );
};
