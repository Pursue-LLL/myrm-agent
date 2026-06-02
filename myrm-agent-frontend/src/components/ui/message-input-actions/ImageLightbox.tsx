import React, { useEffect, useCallback, useState, useMemo, useRef } from 'react';
import { motion, AnimatePresence, useMotionValue, useSpring, useMotionValueEvent } from 'framer-motion';
import { X, ChevronLeft, ChevronRight } from 'lucide-react';
import { File as FileType } from '@/store/useChatStore';
import { getDisplayUrl } from '@/lib/utils/fileUtils';

interface ImageLightboxProps {
  images: FileType[];
  initialIndex: number;
  onClose: () => void;
  layoutIdPrefix?: string;
}

export const ImageLightbox: React.FC<ImageLightboxProps> = ({ images, initialIndex, onClose, layoutIdPrefix = '' }) => {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [isLongImage, setIsLongImage] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  const [isZoomed, setIsZoomed] = useState(false);
  const scale = useMotionValue(1);
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const springConfig = { damping: 30, stiffness: 300 };
  const scaleSpring = useSpring(scale, springConfig);

  useMotionValueEvent(scale, 'change', (latest) => {
    setIsZoomed(latest > 1.05);
  });

  // Reset state when changing images
  const resetTransform = useCallback(() => {
    scale.set(1);
    x.set(0);
    y.set(0);
    setIsLongImage(false);
  }, [scale, x, y]);

  const handlePrevious = useCallback(
    (e?: React.MouseEvent) => {
      e?.stopPropagation();
      setCurrentIndex((prev) => (prev > 0 ? prev - 1 : images.length - 1));
      resetTransform();
    },
    [images.length, resetTransform],
  );

  const handleNext = useCallback(
    (e?: React.MouseEvent) => {
      e?.stopPropagation();
      setCurrentIndex((prev) => (prev < images.length - 1 ? prev + 1 : 0));
      resetTransform();
    },
    [images.length, resetTransform],
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') handlePrevious();
      if (e.key === 'ArrowRight') handleNext();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, handlePrevious, handleNext]);

  const currentImage = images[currentIndex];

  const src = useMemo(() => {
    if (!currentImage) return '';
    return getDisplayUrl(currentImage);
  }, [currentImage]);

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    if (img.naturalHeight > img.naturalWidth * 2.5) {
      setIsLongImage(true);
    } else {
      setIsLongImage(false);
    }
  };

  // Wheel to zoom
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleNativeWheel = (e: WheelEvent) => {
      // If it's a long image and not zoomed, allow native vertical scrolling
      if (isLongImage && scale.get() === 1) return;

      e.preventDefault();
      const zoomSensitivity = 0.005;
      const currentScale = scale.get();
      const newScale = Math.max(0.5, Math.min(currentScale - e.deltaY * zoomSensitivity, 5));

      // Pointer-centric zoom math
      if (imgRef.current) {
        const rect = imgRef.current.getBoundingClientRect();
        const pointerX = e.clientX - rect.left - rect.width / 2;
        const pointerY = e.clientY - rect.top - rect.height / 2;

        const scaleRatio = newScale / currentScale;
        const dx = pointerX * (1 - scaleRatio);
        const dy = pointerY * (1 - scaleRatio);

        x.set(x.get() + dx);
        y.set(y.get() + dy);
      }

      scale.set(newScale);
    };

    container.addEventListener('wheel', handleNativeWheel, { passive: false });
    return () => container.removeEventListener('wheel', handleNativeWheel);
  }, [isLongImage, scale, x, y]);

  // Double click to zoom
  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    const currentScale = scale.get();
    if (currentScale > 1) {
      scale.set(1);
      x.set(0);
      y.set(0);
    } else {
      const newScale = 2.5;
      if (imgRef.current) {
        const rect = imgRef.current.getBoundingClientRect();
        const pointerX = e.clientX - rect.left - rect.width / 2;
        const pointerY = e.clientY - rect.top - rect.height / 2;

        const scaleRatio = newScale / currentScale;
        const dx = pointerX * (1 - scaleRatio);
        const dy = pointerY * (1 - scaleRatio);

        x.set(x.get() + dx);
        y.set(y.get() + dy);
      }
      scale.set(newScale);
    }
  };

  // Swipe down to dismiss
  const handleDragEnd = (e: any, info: any) => {
    if (scale.get() <= 1 && info.offset.y > 100 && info.velocity.y > 200) {
      onClose();
    }
  };

  if (!currentImage || !src) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/90 backdrop-blur-sm"
        onClick={onClose}
      >
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClose();
          }}
          className="absolute top-4 right-4 p-2 text-white/70 hover:text-white bg-black/40 hover:bg-black/60 rounded-full transition-colors z-50"
        >
          <X size={24} />
        </button>

        {images.length > 1 && (
          <>
            <button
              onClick={handlePrevious}
              className="absolute left-4 p-3 text-white/70 hover:text-white bg-black/40 hover:bg-black/60 rounded-full transition-colors z-50"
            >
              <ChevronLeft size={32} />
            </button>
            <button
              onClick={handleNext}
              className="absolute right-4 p-3 text-white/70 hover:text-white bg-black/40 hover:bg-black/60 rounded-full transition-colors z-50"
            >
              <ChevronRight size={32} />
            </button>
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-black/60 rounded-full text-white/90 text-sm font-medium tracking-wider z-50">
              {currentIndex + 1} / {images.length}
            </div>
          </>
        )}

        <div
          ref={containerRef}
          className={`relative w-full h-full flex ${isLongImage && !isZoomed ? 'items-start overflow-auto' : 'items-center overflow-hidden'} justify-center p-4 md:p-12`}
          onClick={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.img
            ref={imgRef}
            layout
            layoutId={`image-${layoutIdPrefix}${currentImage.fileName}`}
            src={src}
            alt={currentImage.fileName}
            onLoad={handleImageLoad}
            onDoubleClick={handleDoubleClick}
            style={{ x, y, scale: scaleSpring }}
            drag={isZoomed || !isLongImage}
            dragConstraints={containerRef}
            dragElastic={0.2}
            onDragEnd={handleDragEnd}
            className={`
              ${isZoomed || !isLongImage ? 'cursor-grab active:cursor-grabbing' : ''}
              ${!isLongImage ? 'max-w-full max-h-full object-contain' : 'w-full max-w-4xl h-auto object-contain mt-8 mb-8'}
              rounded-full shadow-2xl
            `}
          />
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
