/**
 * [INPUT]
 * - FlowPadCapture (POS: FlowPad 截图上下文 DTO)
 * - CapturePreview (POS: 单张截图预览组件)
 *
 * [OUTPUT]
 * - FlowPadCapturesStrip: FlowPad 截图预览条。
 *
 * [POS]
 * 从 FlowPadModal 抽离截图条渲染，降低主组件体积与冲突概率。
 */
import type { FlowPadCapture } from '@/store/useFlowPadStore';

import { CapturePreview } from './FlowPadModalParts';

interface FlowPadCapturesStripProps {
  captures: FlowPadCapture[];
  collapseLabel: string;
  onRemoveCapture: (index: number) => void;
  onOpenLightbox: (src: string) => void;
}

export function FlowPadCapturesStrip({
  captures,
  collapseLabel,
  onRemoveCapture,
  onOpenLightbox,
}: FlowPadCapturesStripProps) {
  return (
    <div className="px-4 py-3 border-b border-border/30 bg-muted/10">
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
        {captures.map((capture, idx) => (
          <CapturePreview
            key={capture.timestamp + idx}
            capture={capture}
            collapseLabel={collapseLabel}
            onRemove={() => onRemoveCapture(idx)}
            onImageClick={() => capture.screenshot && onOpenLightbox(`data:image/jpeg;base64,${capture.screenshot}`)}
          />
        ))}
      </div>
    </div>
  );
}
