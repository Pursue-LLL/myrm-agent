'use client';

import React, { useState, useEffect } from 'react';
import {
  PhoneCall,
  PhoneOff,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Share2,
  ShieldCheck,
  UserCheck,
  Radio,
} from 'lucide-react';
import { useFingerprintStudioStore } from './useFingerprintStudioStore';

export const FullModalityParityCallHUD: React.FC = () => {
  const {
    callSession,
    toggleMute,
    toggleSpeaker,
    toggleScreenShare,
    endCall,
    enterpriseMode,
    setEnterpriseMode,
    auditTrails,
  } = useFingerprintStudioStore();

  const [simulatedVolume, setSimulatedVolume] = useState([30, 65, 45, 80, 55, 90, 40]);

  // 模拟音频声波流跳动
  useEffect(() => {
    if (callSession.state !== 'active' && callSession.state !== 'screen_sharing') {
      return;
    }
    const timer = setInterval(() => {
      setSimulatedVolume((prev) =>
        prev.map(() => Math.floor(Math.random() * 70) + 20)
      );
    }, 200);
    return () => { clearInterval(timer); };
  }, [callSession.state]);

  if (callSession.state === 'idle' || callSession.state === 'ended') {
    return null;
  }

  const latestAudit = auditTrails[0];

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 font-sans select-none animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* HUD Container */}
      <div className="flex items-center gap-4 px-4 py-3 rounded-2xl border border-slate-700 bg-slate-900/95 shadow-2xl backdrop-blur-md text-slate-200">
        {/* Agent Info & Pulse Wave */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-full bg-blue-600/20 border border-blue-500/40 text-blue-300">
            <Radio className="w-5 h-5 animate-pulse" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs text-slate-100">
                {callSession.agentName || '智能体通话'}
              </span>
              {enterpriseMode ? (
                <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-500/30">
                  <ShieldCheck className="w-3 h-3 text-emerald-400" />
                  企业平权·合规审计
                </span>
              ) : (
                <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400">
                  <UserCheck className="w-3 h-3" />
                  个人模式
                </span>
              )}
            </div>

            {/* Simulated Audio Waveform */}
            <div className="flex items-center gap-1 mt-1 h-3">
              {simulatedVolume.map((vol, idx) => (
                <span
                  key={idx}
                  className={`w-0.5 rounded-full transition-all duration-150 ${
                    callSession.isMuted ? 'bg-slate-600' : 'bg-blue-400'
                  }`}
                  style={{ height: `${callSession.isMuted ? 4 : Math.max(4, vol * 0.15)}px` }}
                />
              ))}
              <span className="text-[10px] text-slate-400 ml-1 font-mono">
                {callSession.state === 'screen_sharing' ? '屏幕协同中' : '全双工通话中'}
              </span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
          {/* Mute */}
          <button
            type="button"
            onClick={toggleMute}
            aria-label={callSession.isMuted ? '取消静音' : '麦克风静音'}
            className={`p-2 rounded-full border transition-colors ${
              callSession.isMuted
                ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {callSession.isMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
          </button>

          {/* Speaker */}
          <button
            type="button"
            onClick={toggleSpeaker}
            aria-label={callSession.isSpeakerOn ? '关闭扬声器' : '开启扬声器'}
            className={`p-2 rounded-full border transition-colors ${
              !callSession.isSpeakerOn
                ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {callSession.isSpeakerOn ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
          </button>

          {/* Screen Share */}
          <button
            type="button"
            onClick={toggleScreenShare}
            aria-label={callSession.isScreenSharing ? '停止屏幕共享' : '开始屏幕共享'}
            className={`p-2 rounded-full border transition-colors ${
              callSession.isScreenSharing
                ? 'bg-purple-500/20 border-purple-500/40 text-purple-300 shadow-sm'
                : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <Share2 className="w-4 h-4" />
          </button>

          {/* Hang Up */}
          <button
            type="button"
            onClick={endCall}
            aria-label="挂断通话"
            className="p-2 rounded-full bg-red-600 hover:bg-red-500 text-white transition-colors"
          >
            <PhoneOff className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Enterprise Audit Footer Badge */}
      {enterpriseMode && latestAudit && (
        <div className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800/80 text-[10px] text-slate-400">
          <span className="font-mono text-slate-400 truncate max-w-[240px]">
            {latestAudit.complianceHash}
          </span>
          <span className="text-emerald-400 font-medium">审计链实时存证</span>
        </div>
      )}
    </div>
  );
};
