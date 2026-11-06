import Image from 'next/image';
import { cn } from '@/lib/utils/classnameUtils';

interface BrandLogoProps {
  className?: string;
  size?: number;
  priority?: boolean;
  /** The brand name is already written next to the mark, so the image adds nothing for assistive tech. */
  decorative?: boolean;
}

const BRAND_ICON_SRC = '/brand/brand-mark-128.webp';
const BRAND_ICON_LARGE_SRC = '/brand/brand-mark-256.webp';

function brandIconSrc(displaySize: number): string {
  return displaySize > 64 ? BRAND_ICON_LARGE_SRC : BRAND_ICON_SRC;
}

export default function BrandLogo({ className, size = 40, priority = false, decorative = false }: BrandLogoProps) {
  return (
    <Image
      src={brandIconSrc(size)}
      alt={decorative ? '' : 'MyrmAgent'}
      width={size}
      height={size}
      priority={priority}
      unoptimized
      className={cn('shrink-0 object-contain', className)}
    />
  );
}
