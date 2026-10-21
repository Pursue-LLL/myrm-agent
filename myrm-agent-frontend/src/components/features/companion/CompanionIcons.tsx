/**
 * Companion Species SVG Icons — unified style, theme-adaptive via currentColor.
 * Each icon renders at the given size (default 24px) with rounded, friendly aesthetics.
 */
import type { FC, SVGProps } from 'react';

interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

const defaults = (size: number, props: SVGProps<SVGSVGElement>) => ({
  width: size,
  height: size,
  viewBox: '0 0 32 32',
  fill: 'none',
  xmlns: 'http://www.w3.org/2000/svg',
  ...props,
});

export const IconCat: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <path d="M6 8L9 4L12 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M20 8L23 4L26 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <ellipse cx="16" cy="18" rx="10" ry="10" stroke="currentColor" strokeWidth="2" />
    <circle cx="12" cy="16" r="1.5" fill="currentColor" />
    <circle cx="20" cy="16" r="1.5" fill="currentColor" />
    <path d="M14 20Q16 22 18 20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path
      d="M7 18H3M25 18H29M7 16L3 15M25 16L29 15"
      stroke="currentColor"
      strokeWidth="1"
      strokeLinecap="round"
      opacity="0.5"
    />
  </svg>
);

export const IconDog: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <ellipse cx="16" cy="18" rx="10" ry="10" stroke="currentColor" strokeWidth="2" />
    <path d="M6 12Q4 6 8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    <path d="M26 12Q28 6 24 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    <circle cx="12" cy="16" r="1.5" fill="currentColor" />
    <circle cx="20" cy="16" r="1.5" fill="currentColor" />
    <ellipse cx="16" cy="21" rx="3" ry="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="16" cy="20" r="1" fill="currentColor" />
    <path d="M14 23Q16 25 18 23" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
);

export const IconBear: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <circle cx="8" cy="8" r="4" stroke="currentColor" strokeWidth="2" />
    <circle cx="24" cy="8" r="4" stroke="currentColor" strokeWidth="2" />
    <ellipse cx="16" cy="18" rx="11" ry="11" stroke="currentColor" strokeWidth="2" />
    <circle cx="12" cy="16" r="1.5" fill="currentColor" />
    <circle cx="20" cy="16" r="1.5" fill="currentColor" />
    <ellipse cx="16" cy="20" rx="2.5" ry="1.5" fill="currentColor" opacity="0.3" />
    <circle cx="16" cy="19.5" r="1" fill="currentColor" />
    <path d="M14 22Q16 24 18 22" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
);

export const IconRabbit: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <path d="M11 12V3Q11 1 13 1Q15 1 15 3V12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    <path d="M17 12V3Q17 1 19 1Q21 1 21 3V12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    <ellipse cx="16" cy="20" rx="9" ry="9" stroke="currentColor" strokeWidth="2" />
    <circle cx="13" cy="18" r="1.5" fill="currentColor" />
    <circle cx="19" cy="18" r="1.5" fill="currentColor" />
    <path d="M14.5 22Q16 23.5 17.5 22" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    <circle cx="11" cy="21" r="2" fill="currentColor" opacity="0.15" />
    <circle cx="21" cy="21" r="2" fill="currentColor" opacity="0.15" />
  </svg>
);

export const IconOwl: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <ellipse cx="16" cy="18" rx="10" ry="11" stroke="currentColor" strokeWidth="2" />
    <path d="M6 10L10 7L14 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M18 10L22 7L26 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="12" cy="15" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="20" cy="15" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="15" r="1.2" fill="currentColor" />
    <circle cx="20" cy="15" r="1.2" fill="currentColor" />
    <path d="M15 20L16 22L17 20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconDragon: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <path d="M8 6L6 2L10 5M24 6L26 2L22 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <ellipse cx="16" cy="18" rx="10" ry="10" stroke="currentColor" strokeWidth="2" />
    <circle cx="12" cy="15" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="20" cy="15" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="15" r="0.8" fill="currentColor" />
    <circle cx="20" cy="15" r="0.8" fill="currentColor" />
    <path d="M12 22Q16 26 20 22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M13 23L14 25M19 23L18 25" stroke="currentColor" strokeWidth="1" strokeLinecap="round" opacity="0.5" />
  </svg>
);

export const IconSloth: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <ellipse cx="16" cy="18" rx="10" ry="10" stroke="currentColor" strokeWidth="2" />
    <circle cx="12" cy="16" r="3" fill="currentColor" opacity="0.1" />
    <circle cx="20" cy="16" r="3" fill="currentColor" opacity="0.1" />
    <path d="M11 16H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M19 16H21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M14 21Q16 22 18 21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="16" cy="19" r="1.5" fill="currentColor" opacity="0.3" />
  </svg>
);

export const IconPenguin: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <ellipse cx="16" cy="18" rx="9" ry="11" stroke="currentColor" strokeWidth="2" />
    <ellipse cx="16" cy="20" rx="5" ry="7" stroke="currentColor" strokeWidth="1" opacity="0.3" />
    <circle cx="12" cy="14" r="1.5" fill="currentColor" />
    <circle cx="20" cy="14" r="1.5" fill="currentColor" />
    <path
      d="M14 19L16 21L18 19"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      fill="currentColor"
      opacity="0.4"
    />
    <path
      d="M6 16Q3 20 7 24M26 16Q29 20 25 24"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      fill="none"
    />
  </svg>
);

export const IconFox: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <path d="M6 14L4 4L12 10" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" fill="none" />
    <path d="M26 14L28 4L20 10" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" fill="none" />
    <ellipse cx="16" cy="19" rx="10" ry="9" stroke="currentColor" strokeWidth="2" />
    <circle cx="12" cy="16" r="1.5" fill="currentColor" />
    <circle cx="20" cy="16" r="1.5" fill="currentColor" />
    <path d="M16 20V22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M14 22Q16 24 18 22" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
);

export const IconOctopus: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <ellipse cx="16" cy="13" rx="9" ry="8" stroke="currentColor" strokeWidth="2" />
    <circle cx="12" cy="12" r="1.5" fill="currentColor" />
    <circle cx="20" cy="12" r="1.5" fill="currentColor" />
    <path d="M14 16Q16 18 18 16" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    <path
      d="M8 20Q6 26 8 28M11 21Q10 27 12 28M16 22Q16 28 16 28M21 21Q22 27 20 28M24 20Q26 26 24 28"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      fill="none"
    />
  </svg>
);

export const IconCactus: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <rect x="13" y="6" width="6" height="20" rx="3" stroke="currentColor" strokeWidth="2" />
    <path d="M13 14H8Q6 14 6 16Q6 18 8 18H13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none" />
    <path
      d="M19 18H24Q26 18 26 20Q26 22 24 22H19"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      fill="none"
    />
    <circle cx="14.5" cy="12" r="0.8" fill="currentColor" />
    <circle cx="17.5" cy="12" r="0.8" fill="currentColor" />
    <path d="M15 15Q16 16 17 15" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
  </svg>
);

export const IconRobot: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <rect x="6" y="10" width="20" height="16" rx="3" stroke="currentColor" strokeWidth="2" />
    <path d="M16 10V6M14 6H18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <rect x="10" y="15" width="4" height="3" rx="1" fill="currentColor" opacity="0.6" />
    <rect x="18" y="15" width="4" height="3" rx="1" fill="currentColor" opacity="0.6" />
    <path d="M12 22H20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M4 16V20M28 16V20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

export const IconMushroom: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <path d="M4 16Q4 6 16 6Q28 6 28 16Z" stroke="currentColor" strokeWidth="2" fill="none" />
    <circle cx="10" cy="12" r="2" fill="currentColor" opacity="0.2" />
    <circle cx="18" cy="10" r="2.5" fill="currentColor" opacity="0.2" />
    <circle cx="22" cy="14" r="1.5" fill="currentColor" opacity="0.2" />
    <rect x="12" y="16" width="8" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
    <circle cx="14" cy="20" r="1" fill="currentColor" />
    <circle cx="18" cy="20" r="1" fill="currentColor" />
    <path d="M15 23Q16 24 17 23" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
  </svg>
);

export const IconPanda: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <circle cx="8" cy="8" r="4" fill="currentColor" opacity="0.3" />
    <circle cx="24" cy="8" r="4" fill="currentColor" opacity="0.3" />
    <ellipse cx="16" cy="18" rx="11" ry="11" stroke="currentColor" strokeWidth="2" />
    <ellipse cx="11" cy="15" rx="3.5" ry="3" fill="currentColor" opacity="0.3" />
    <ellipse cx="21" cy="15" rx="3.5" ry="3" fill="currentColor" opacity="0.3" />
    <circle cx="11" cy="15" r="1.5" fill="currentColor" />
    <circle cx="21" cy="15" r="1.5" fill="currentColor" />
    <ellipse cx="16" cy="20" rx="2" ry="1.2" fill="currentColor" opacity="0.3" />
    <circle cx="16" cy="19.5" r="1" fill="currentColor" />
    <path d="M14 22Q16 24 18 22" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </svg>
);

export const IconFrog: FC<IconProps> = ({ size = 24, ...props }) => (
  <svg {...defaults(size, props)}>
    <circle cx="10" cy="8" r="4" stroke="currentColor" strokeWidth="2" />
    <circle cx="22" cy="8" r="4" stroke="currentColor" strokeWidth="2" />
    <circle cx="10" cy="8" r="1.5" fill="currentColor" />
    <circle cx="22" cy="8" r="1.5" fill="currentColor" />
    <ellipse cx="16" cy="20" rx="11" ry="9" stroke="currentColor" strokeWidth="2" />
    <path d="M10 22Q16 28 22 22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none" />
    <circle cx="12" cy="19" r="2" fill="currentColor" opacity="0.1" />
    <circle cx="20" cy="19" r="2" fill="currentColor" opacity="0.1" />
  </svg>
);

/** Hat SVG icons — consistent with PremiumIcons style */

export const HatCrown: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <path d="M2 12H14L15 5L11 8L8 3L5 8L1 5L2 12Z" fill="currentColor" />
    <rect x="2" y="12" width="12" height="1.5" rx="0.5" fill="currentColor" />
  </svg>
);

export const HatTophat: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <rect x="4" y="3" width="8" height="8" rx="1" fill="currentColor" opacity="0.8" />
    <rect x="2" y="11" width="12" height="2" rx="1" fill="currentColor" />
  </svg>
);

export const HatStar: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <path d="M8 1L9.8 5.8L15 6.4L11.2 9.8L12.4 15L8 12.2L3.6 15L4.8 9.8L1 6.4L6.2 5.8L8 1Z" fill="currentColor" />
  </svg>
);

export const HatWizard: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <path d="M8 1L3 14H13L8 1Z" stroke="currentColor" strokeWidth="1.5" fill="currentColor" opacity="0.3" />
    <circle cx="7" cy="7" r="1" fill="currentColor" />
    <circle cx="9" cy="10" r="0.8" fill="currentColor" />
    <rect x="2" y="13" width="12" height="2" rx="1" fill="currentColor" />
  </svg>
);

export const HatBow: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <path d="M8 8C6 6 2 5 2 8C2 11 6 10 8 8Z" fill="currentColor" opacity="0.6" />
    <path d="M8 8C10 6 14 5 14 8C14 11 10 10 8 8Z" fill="currentColor" opacity="0.6" />
    <circle cx="8" cy="8" r="1.5" fill="currentColor" />
    <path d="M7 10Q8 14 9 10" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
  </svg>
);

export const HatFlower: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <circle cx="8" cy="5" r="2.5" fill="currentColor" opacity="0.3" />
    <circle cx="5" cy="7.5" r="2.5" fill="currentColor" opacity="0.3" />
    <circle cx="11" cy="7.5" r="2.5" fill="currentColor" opacity="0.3" />
    <circle cx="6" cy="10.5" r="2.5" fill="currentColor" opacity="0.3" />
    <circle cx="10" cy="10.5" r="2.5" fill="currentColor" opacity="0.3" />
    <circle cx="8" cy="8" r="2" fill="currentColor" />
  </svg>
);

export const HatFire: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <path
      d="M8 1C8 1 4 6 4 10C4 12.5 5.8 15 8 15C10.2 15 12 12.5 12 10C12 6 8 1 8 1Z"
      fill="currentColor"
      opacity="0.5"
    />
    <path
      d="M8 6C8 6 6 9 6 11C6 12.5 6.8 14 8 14C9.2 14 10 12.5 10 11C10 9 8 6 8 6Z"
      fill="currentColor"
      opacity="0.7"
    />
  </svg>
);

export const HatIce: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <path d="M8 1V15M1 8H15M3 3L13 13M13 3L3 13" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    <circle cx="8" cy="8" r="2" fill="currentColor" opacity="0.3" />
  </svg>
);

export const HatGrad: FC<IconProps> = ({ size = 12, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" {...props}>
    <path d="M8 2L1 6L8 10L15 6L8 2Z" fill="currentColor" />
    <path
      d="M3 7.5V12C3 12 5.5 14 8 14C10.5 14 13 12 13 12V7.5"
      stroke="currentColor"
      strokeWidth="1"
      strokeLinecap="round"
    />
    <path d="M14 6V11" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
  </svg>
);

/** Mapping from species emoji to SVG component */
export const SPECIES_ICON_MAP: Record<string, FC<IconProps>> = {
  '🐱': IconCat,
  '🐶': IconDog,
  '🐻': IconBear,
  '🐰': IconRabbit,
  '🦉': IconOwl,
  '🐲': IconDragon,
  '🦥': IconSloth,
  '🐧': IconPenguin,
  '🦊': IconFox,
  '🐙': IconOctopus,
  '🌵': IconCactus,
  '🤖': IconRobot,
  '🍄': IconMushroom,
  '🐼': IconPanda,
  '🐸': IconFrog,
};

/** Mapping from hat emoji to SVG component */
export const HAT_ICON_MAP: Record<string, FC<IconProps>> = {
  '👑': HatCrown,
  '🎩': HatTophat,
  '⭐': HatStar,
  '🧙': HatWizard,
  '🎀': HatBow,
  '🌸': HatFlower,
  '🔥': HatFire,
  '❄️': HatIce,
  '🎓': HatGrad,
};
