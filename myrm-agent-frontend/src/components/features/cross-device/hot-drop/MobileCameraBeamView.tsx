/**
 * Mobile Camera Beam View Component
 * 手机端瞬态外设无线相机与素材枪：支持拍照/相册选图与 1 秒直投桌面输入框
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 移动端触控优化与无障碍标准。
 */

import React, { useState, useRef } from 'react';
import {
  Camera,
  Image as ImageIcon,
  ArrowUpRight,
  CheckCircle2,
  Sparkles,
  Laptop,
  RotateCcw,
} from 'lucide-react';
import { useCrossDeviceDropStore } from './useCrossDeviceDropStore';
import {
  createMockBeamPayload,
  formatByteSize,
  validateBeamFile,
} from './beamTransportProtocol';

export interface MobileCameraBeamViewProps {
  className?: string;
  onBeamComplete?: () => void;
}

export const MobileCameraBeamView: React.FC<MobileCameraBeamViewProps> = ({
  className = '',
  onBeamComplete,
}) => {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [fileDetails, setFileDetails] = useState<{
    name: string;
    size: number;
    type: string;
  } | null>(null);
  const [suggestedPrompt, setSuggestedPrompt] = useState<string>(
    '请分析拍摄的白板内容，提取核心待办与架构拓扑'
  );
  const [isSending, setIsSending] = useState<boolean>(false);
  const [isSuccess, setIsSuccess] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const { activeSession, receivePayload } = useCrossDeviceDropStore();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (!file) {
      return;
    }

    const validation = validateBeamFile(file.size, file.type);
    if (!validation.isValid) {
      setErrorMessage(validation.errorMessage || '文件不符合要求');
      return;
    }

    setErrorMessage(null);
    setFileDetails({
      name: file.name,
      size: file.size,
      type: file.type,
    });

    const reader = new FileReader();
    reader.onload = (event) => {
      if (typeof event.target?.result === 'string') {
        setSelectedImage(event.target.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleInstantBeam = (): void => {
    setIsSending(true);

    // 构造投送 Payload
    const payload = selectedImage
      ? {
          id: `payload-${Date.now()}`,
          sourceDeviceName: 'Mobile Device (Live)',
          fileName: fileDetails?.name || 'capture.jpg',
          fileSizeBytes: fileDetails?.size || 1_200_000,
          mimeType: fileDetails?.type || 'image/jpeg',
          dataUrl: selectedImage,
          capturedTimestamp: Date.now(),
          suggestedPrompt,
        }
      : createMockBeamPayload('Mobile Gun', suggestedPrompt);

    setTimeout(() => {
      receivePayload(payload);
      setIsSending(false);
      setIsSuccess(true);
      if (onBeamComplete) {
        onBeamComplete();
      }
    }, 400);
  };

  const handleReset = (): void => {
    setSelectedImage(null);
    setFileDetails(null);
    setIsSuccess(false);
    setErrorMessage(null);
  };

  return (
    <div
      data-testid="mobile-camera-beam-view"
      className={`flex flex-col rounded-2xl border border-neutral-800 bg-neutral-950 p-5 text-neutral-100 shadow-2xl max-w-md mx-auto space-y-4 ${className}`}
    >
      {/* 顶部目标电脑指示条 */}
      <div className="flex items-center justify-between border-b border-neutral-800/80 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
            <Laptop className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs font-semibold text-white">
              直连目标：Myrm 桌面端
            </div>
            <div className="font-mono text-[10px] text-neutral-400">
              配对短码：{activeSession.pairCode}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 font-mono text-[10px] text-emerald-400">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>通道已就绪</span>
        </div>
      </div>

      {/* 隐藏原生文件输入项（支持系统相机拉起） */}
      <input
        type="file"
        ref={fileInputRef}
        accept="image/*"
        capture="environment"
        onChange={handleFileChange}
        className="hidden"
        data-testid="camera-file-input"
      />

      {/* 核心拍摄与相册触发区 */}
      {!selectedImage && !isSuccess && (
        <div className="grid grid-cols-2 gap-3 py-2">
          <button
            type="button"
            data-testid="open-camera-btn"
            onClick={() => {
              fileInputRef.current?.click();
            }}
            className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-indigo-500/40 bg-indigo-950/20 p-6 text-indigo-300 hover:border-indigo-400 hover:bg-indigo-950/40 transition-colors"
          >
            <Camera className="h-8 w-8 text-indigo-400" />
            <span className="text-xs font-medium">唤起相机拍摄</span>
          </button>

          <button
            type="button"
            data-testid="open-gallery-btn"
            onClick={() => {
              if (fileInputRef.current) {
                fileInputRef.current.removeAttribute('capture');
                fileInputRef.current.click();
              }
            }}
            className="flex flex-col items-center justify-center gap-2 rounded-xl border border-neutral-800 bg-neutral-900/60 p-6 text-neutral-300 hover:border-neutral-700 hover:bg-neutral-900 transition-colors"
          >
            <ImageIcon className="h-8 w-8 text-neutral-400" />
            <span className="text-xs font-medium">从相册选取</span>
          </button>
        </div>
      )}

      {errorMessage && (
        <div className="rounded-lg bg-rose-950/40 border border-rose-800/60 p-2.5 text-xs text-rose-300">
          {errorMessage}
        </div>
      )}

      {/* 拍摄完成预览与附带指令 */}
      {selectedImage && !isSuccess && (
        <div className="space-y-3" data-testid="beam-preview-container">
          <div className="relative overflow-hidden rounded-xl border border-neutral-800 bg-neutral-900">
            {/* oxlint-disable-next-line next/no-img-element */}
            <img
              src={selectedImage}
              alt="拍摄预览"
              className="h-44 w-full object-cover"
              data-testid="preview-image-elem"
            />
            {fileDetails && (
              <div className="absolute bottom-2 left-2 rounded-md bg-neutral-950/80 px-2 py-0.5 text-[10px] font-mono text-neutral-300 backdrop-blur-sm">
                {fileDetails.name} · {formatByteSize(fileDetails.size)}
              </div>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="prompt-instruction-input"
              className="flex items-center gap-1 text-[11px] text-neutral-400 font-medium"
            >
              <Sparkles className="h-3 w-3 text-indigo-400" />
              <span>附带分析指令（可选）</span>
            </label>
            <input
              id="prompt-instruction-input"
              type="text"
              value={suggestedPrompt}
              onChange={(e) => {
                setSuggestedPrompt(e.target.value);
              }}
              data-testid="beam-prompt-input"
              className="w-full rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-xs text-white placeholder-neutral-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              data-testid="retake-photo-btn"
              onClick={handleReset}
              className="flex items-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-xs text-neutral-300 hover:bg-neutral-800"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>重拍</span>
            </button>

            <button
              type="button"
              data-testid="instant-beam-submit-btn"
              disabled={isSending}
              onClick={handleInstantBeam}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors shadow-md disabled:opacity-50"
            >
              <ArrowUpRight className="h-4 w-4" />
              <span>
                {isSending ? '正在热直投中...' : '1秒直投至桌面输入框'}
              </span>
            </button>
          </div>
        </div>
      )}

      {/* 投送成功状态 */}
      {isSuccess && (
        <div
          data-testid="beam-success-card"
          className="flex flex-col items-center justify-center rounded-xl bg-emerald-950/30 border border-emerald-500/40 p-6 text-center space-y-2"
        >
          <CheckCircle2 className="h-10 w-10 text-emerald-400 animate-bounce" />
          <div className="text-sm font-semibold text-emerald-200">
            素材已成功直达电脑光标！
          </div>
          <p className="text-xs text-neutral-400 max-w-xs">
            桌面端输入框已就绪，并在电脑上敲击 Enter 即可开启 Agent 理解分析。
          </p>

          <button
            type="button"
            data-testid="beam-again-btn"
            onClick={handleReset}
            className="mt-3 flex items-center gap-1 text-xs text-indigo-400 hover:underline"
          >
            <span>再投送一张</span>
          </button>
        </div>
      )}
    </div>
  );
};
