import React from 'react';
import { Check, Crosshair } from 'lucide-react';
import { useElementPatchStore } from './useElementPatchStore';
import { ElementAnnotationItem } from './elementPatchTypes';

export interface ElementAnnotationPinOverlayProps {
  annotations?: ElementAnnotationItem[];
  className?: string;
}

export const ElementAnnotationPinOverlay: React.FC<ElementAnnotationPinOverlayProps> = ({
  annotations: propAnnotations,
  className = '',
}) => {
  const {
    stagedAnnotations: storeAnnotations,
    selectedAnnotationId,
    selectAnnotation,
    toggleDrawer,
  } = useElementPatchStore();

  const annotations = propAnnotations || storeAnnotations;

  if (annotations.length === 0) {
    return null;
  }

  const handlePinClick = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    selectAnnotation(id);
    toggleDrawer(true);
  };

  return (
    <div
      data-testid="element-annotation-pin-overlay"
      className={`absolute inset-0 pointer-events-none z-30 ${className}`}
    >
      {annotations.map((ann, idx) => {
        const isSelected = selectedAnnotationId === ann.id;
        const isResolved = ann.status === 'resolved';
        const isFailed = ann.status === 'failed';

        let badgeBg = 'bg-indigo-600 border-indigo-400 text-white';
        if (isResolved) {
          badgeBg = 'bg-emerald-600 border-emerald-400 text-white shadow-[0_0_12px_rgba(16,185,129,0.5)]';
        } else if (isFailed) {
          badgeBg = 'bg-red-600 border-red-400 text-white';
        }

        return (
          <div
            key={ann.id}
            data-testid={`annotation-pin-${ann.id}`}
            style={{
              left: `${ann.boundingBox.x}px`,
              top: `${ann.boundingBox.y}px`,
              width: `${ann.boundingBox.width}px`,
              height: `${ann.boundingBox.height}px`,
            }}
            className={`absolute pointer-events-auto border transition-all duration-300 ${
              isSelected
                ? 'border-indigo-400 bg-indigo-500/10 shadow-[0_0_15px_rgba(99,102,241,0.3)]'
                : isResolved
                ? 'border-emerald-500/40 bg-emerald-500/5'
                : 'border-indigo-500/30 bg-indigo-500/5 hover:border-indigo-400'
            }`}
          >
            {/* 元素右上角或正上方的微型悬浮标记 */}
            <button
              type="button"
              onClick={(e) => {
                handlePinClick(e, ann.id);
              }}
              aria-label={`查看第 ${idx + 1} 处元素批注: ${ann.selector}`}
              title={`${idx + 1}. ${ann.selector}: ${ann.instruction}`}
              className={`absolute -top-3.5 -right-3.5 w-7 h-7 rounded-full border-2 flex items-center justify-center text-xs font-bold font-mono transition-transform hover:scale-110 shadow-lg cursor-pointer ${badgeBg}`}
            >
              {isResolved ? (
                <Check className="w-3.5 h-3.5 stroke-[3]" />
              ) : (
                <span>{idx + 1}</span>
              )}
            </button>
          </div>
        );
      })}
    </div>
  );
};
