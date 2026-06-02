'use client';

import * as React from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

type CarouselApi = {
  scrollNext: () => void;
  scrollPrev: () => void;
  canScrollNext: boolean;
  canScrollPrev: boolean;
};

type CarouselProps = {
  orientation?: 'horizontal' | 'vertical';
  opts?: {
    align?: 'start' | 'center' | 'end';
    loop?: boolean;
  };
  setApi?: (api: CarouselApi) => void;
  plugins?: any[];
  className?: string;
  children: React.ReactNode;
};

type CarouselContextProps = {
  carouselRef: React.RefObject<HTMLDivElement | null>;
  api: CarouselApi | null;
  opts?: {
    align?: 'start' | 'center' | 'end';
    loop?: boolean;
  };
  orientation: 'horizontal' | 'vertical';
  scrollPrev: () => void;
  scrollNext: () => void;
  canScrollPrev: boolean;
  canScrollNext: boolean;
};

const CarouselContext = React.createContext<CarouselContextProps | null>(null);

function useCarousel() {
  const context = React.useContext(CarouselContext);

  if (!context) {
    throw new Error('useCarousel must be used within a <Carousel />');
  }

  return context;
}

const Carousel = React.forwardRef<HTMLDivElement, CarouselProps>(
  ({ orientation = 'horizontal', opts, setApi, className, children, ...props }, ref) => {
    const [emblaRef] = React.useState<HTMLDivElement | null>(null);
    const [api, setApiState] = React.useState<CarouselApi | null>(null);

    React.useEffect(() => {
      if (!emblaRef) return;

      // Simple carousel implementation without embla-carousel dependency
      const container = emblaRef;
      const slides = Array.from(container.children) as HTMLElement[];
      let currentIndex = 0;

      const scrollToIndex = (index: number) => {
        if (index < 0 || index >= slides.length) return;
        currentIndex = index;

        // Check if we need vertical or horizontal scrolling
        const computedStyle = window.getComputedStyle(container);
        const isVertical = computedStyle.flexDirection === 'column';

        if (isVertical) {
          const slideHeight = slides[0]?.offsetHeight || 0;
          container.scrollTo({
            top: index * slideHeight,
            behavior: 'smooth',
          });
        } else {
          const slideWidth = slides[0]?.offsetWidth || 0;
          container.scrollTo({
            left: index * slideWidth,
            behavior: 'smooth',
          });
        }
      };

      const scrollNext = () => {
        const nextIndex = opts?.loop
          ? (currentIndex + 1) % slides.length
          : Math.min(currentIndex + 1, slides.length - 1);
        scrollToIndex(nextIndex);
      };

      const scrollPrev = () => {
        const prevIndex = opts?.loop
          ? (currentIndex - 1 + slides.length) % slides.length
          : Math.max(currentIndex - 1, 0);
        scrollToIndex(prevIndex);
      };

      const canScrollNext = () => !opts?.loop && currentIndex < slides.length - 1;
      const canScrollPrev = () => !opts?.loop && currentIndex > 0;

      const carouselApi: CarouselApi = {
        scrollNext,
        scrollPrev,
        get canScrollNext() {
          return canScrollNext();
        },
        get canScrollPrev() {
          return canScrollPrev();
        },
      };

      setApiState(carouselApi);
      setApi?.(carouselApi);
    }, [emblaRef, opts, setApi]);

    return (
      <CarouselContext.Provider
        value={{
          carouselRef: { current: emblaRef },
          api,
          opts,
          orientation,
          scrollPrev: api?.scrollPrev || (() => {}),
          scrollNext: api?.scrollNext || (() => {}),
          canScrollPrev: api?.canScrollPrev || false,
          canScrollNext: api?.canScrollNext || false,
        }}
      >
        <div ref={ref} className={cn('relative', className)} role="region" aria-roledescription="carousel" {...props}>
          {children}
        </div>
      </CarouselContext.Provider>
    );
  },
);
Carousel.displayName = 'Carousel';

const CarouselContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => {
    const { orientation } = useCarousel();

    return (
      <div
        ref={ref}
        className={cn(
          orientation === 'horizontal'
            ? 'flex gap-4 overflow-x-auto scrollbar-hide scroll-smooth'
            : 'flex flex-col gap-4 overflow-y-auto scrollbar-hide scroll-smooth max-h-64',
          className,
        )}
        style={{
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          scrollBehavior: 'smooth',
        }}
        {...props}
      />
    );
  },
);
CarouselContent.displayName = 'CarouselContent';

const CarouselItem = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        role="group"
        aria-roledescription="slide"
        className={cn('min-w-0 shrink-0', className)}
        {...props}
      />
    );
  },
);
CarouselItem.displayName = 'CarouselItem';

const CarouselPrevious = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ className, ...props }, ref) => {
    const { orientation, scrollPrev, canScrollPrev } = useCarousel();

    return (
      <button
        ref={ref}
        className={cn(
          'absolute h-8 w-8 rounded-full border bg-background flex items-center justify-center shadow-md hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
          orientation === 'horizontal' ? 'left-2 top-1/2 -translate-y-1/2' : 'top-2 left-1/2 -translate-x-1/2',
          className,
        )}
        disabled={!canScrollPrev}
        onClick={scrollPrev}
        {...props}
      >
        <ChevronUp className="h-4 w-4" />
        <span className="sr-only">Previous</span>
      </button>
    );
  },
);
CarouselPrevious.displayName = 'CarouselPrevious';

const CarouselNext = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ className, ...props }, ref) => {
    const { orientation, scrollNext, canScrollNext } = useCarousel();

    return (
      <button
        ref={ref}
        className={cn(
          'absolute h-8 w-8 rounded-full border bg-background flex items-center justify-center shadow-md hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
          orientation === 'horizontal' ? 'right-2 top-1/2 -translate-y-1/2' : 'bottom-2 left-1/2 -translate-x-1/2',
          className,
        )}
        disabled={!canScrollNext}
        onClick={scrollNext}
        {...props}
      >
        <ChevronDown className="h-4 w-4" />
        <span className="sr-only">Next</span>
      </button>
    );
  },
);
CarouselNext.displayName = 'CarouselNext';

export { type CarouselApi, Carousel, CarouselContent, CarouselItem, CarouselPrevious, CarouselNext };
