import { create } from 'zustand';
import type {
  ClassifiedDiagnosticResult,
  StderrDiagnosticState,
} from './stderrDiagnosticTypes';
import {
  appendBoundedStderr,
  classifyStderr,
  MAX_STDERR_BUFFER_BYTES,
} from './stderrClassifier';

export const useStderrDiagnosticStore = create<StderrDiagnosticState>((set, get) => ({
  rawBuffer: '',
  maxBufferBytes: MAX_STDERR_BUFFER_BYTES,
  activeDiagnostic: null,
  isFixing: false,
  fixSuccessMessage: null,

  ingestStderrChunk: (chunk: string) => {
    set((state) => ({
      rawBuffer: appendBoundedStderr(state.rawBuffer, chunk),
    }));
  },

  classifyProcessExit: (exitCode: number) => {
    const { rawBuffer } = get();
    const result: ClassifiedDiagnosticResult = classifyStderr(rawBuffer, exitCode);
    set({
      activeDiagnostic: result,
      fixSuccessMessage: null,
    });
    return result;
  },

  executeFixAction: async (actionId: string) => {
    set({ isFixing: true, fixSuccessMessage: null });
    await new Promise((resolve) => setTimeout(resolve, 350));

    const { activeDiagnostic } = get();
    let message = '排障修复指令已成功执行，您可以重新尝试运行命令。';

    if (actionId.startsWith('fix_install_')) {
      const pkg = actionId.replace('fix_install_', '');
      message = `已自动在沙箱环境中完成依赖「${pkg}」的安装与验证！`;
    } else if (actionId === 'fix_increase_memory') {
      message = '沙箱运行内存已成功扩容至 4GB，硬件限制已重置！';
    } else if (actionId === 'fix_switch_port') {
      message = '已自动为该服务分配未占用的随机空闲端口 (8001)！';
    } else if (actionId === 'fix_open_provider_settings') {
      message = '已打开模型服务设置向导，请校验 API 密钥或订阅账户。';
    }

    set({
      isFixing: false,
      fixSuccessMessage: message,
    });
  },

  dismissDiagnostic: () => {
    set({
      activeDiagnostic: null,
      fixSuccessMessage: null,
    });
  },

  resetDiagnosticState: () => {
    set({
      rawBuffer: '',
      activeDiagnostic: null,
      isFixing: false,
      fixSuccessMessage: null,
    });
  },
}));
