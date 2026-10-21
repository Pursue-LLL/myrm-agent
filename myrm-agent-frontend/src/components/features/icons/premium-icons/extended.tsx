import type { IconProps } from './types';

export const IconClock = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M7.5 1C4.46 1 2 3.46 2 6.5C2 9.54 4.46 12 7.5 12C10.54 12 13 9.54 13 6.5C13 3.46 10.54 1 7.5 1ZM2 6.5C2 3.46 4.46 1 7.5 1C10.54 1 13 3.46 13 6.5C13 9.54 10.54 12 7.5 12C4.46 12 2 9.54 2 6.5Z"
      fill="currentColor"
    />
    <path d="M7.5 3.5V7L10 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconChat = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M2 3C2 2.44772 2.44772 2 3 2H12C12.5523 2 13 2.44772 13 3V9C13 9.55228 12.5523 10 12 10H5L2.5 12.5V10H3C2.44772 10 2 9.55228 2 9V3Z"
      fill="currentColor"
    />
  </svg>
);

export const IconTarget = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <circle cx="7.5" cy="7.5" r="6" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="7.5" cy="7.5" r="4" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="7.5" cy="7.5" r="1.5" fill="currentColor" />
  </svg>
);

export const IconChart = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <rect x="1" y="8" width="3" height="6" rx="0.5" fill="currentColor" />
    <rect x="6" y="4" width="3" height="10" rx="0.5" fill="currentColor" />
    <rect x="11" y="1" width="3" height="13" rx="0.5" fill="currentColor" />
  </svg>
);

export const IconCheckCircle = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <circle cx="7.5" cy="7.5" r="6" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <path
      d="M5 7.5L7 9.5L10.5 5.5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const IconImage = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <rect x="1" y="2" width="13" height="11" rx="1" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="4.5" cy="5" r="1.5" fill="currentColor" />
    <path
      d="M1 11L4.5 7L7.5 10L10 7.5L14 11"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const IconFilm = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <rect x="1" y="2" width="13" height="11" rx="1" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <rect x="3" y="2" width="2" height="2" fill="currentColor" />
    <rect x="3" y="11" width="2" height="2" fill="currentColor" />
    <rect x="10" y="2" width="2" height="2" fill="currentColor" />
    <rect x="10" y="11" width="2" height="2" fill="currentColor" />
    <path d="M6 6L10 8.5L6 11V6Z" fill="currentColor" />
  </svg>
);

export const IconPdf = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M3 1C2.44772 1 2 1.44772 2 2V13C2 13.5523 2.44772 14 3 14H12C12.5523 14 13 13.5523 13 13V5L9 1H3Z"
      fill="currentColor"
    />
    <path d="M9 1V5H13" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    <text x="4" y="11" font-size="5" font-weight="bold" fill="var(--background, #fdfdfb)" font-family="sans-serif">
      PDF
    </text>
  </svg>
);

export const IconTrash = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path d="M5.5 2H9.5C9.5 1.44772 9.05228 1 8.5 1H6.5C5.94772 1 5.5 1.44772 5.5 2Z" fill="currentColor" />
    <path
      d="M3 3H12C12.5523 3 13 3.44772 13 4V5C13 5.55228 12.5523 6 12 6H3C2.44772 6 2 5.55228 2 5V4C2 3.44772 2.44772 3 3 3Z"
      fill="currentColor"
    />
    <path d="M3.5 6H4.5L5 13H10L10.5 6H11.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
  </svg>
);

export const IconUndo = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M4 4H10C11.6569 4 13 5.34315 13 7C13 8.65685 11.6569 10 10 10H7"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path d="M6 2L3 5L6 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconBriefcase = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <rect x="1" y="4" width="13" height="9" rx="1" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <path
      d="M5 4V2.5C5 2.22386 5.22386 2 5.5 2H9.5C9.77614 2 10 2.22386 10 2.5V4"
      stroke="currentColor"
      strokeWidth="1.5"
    />
    <rect x="6" y="7" width="3" height="2" rx="0.5" fill="currentColor" />
  </svg>
);

export const IconBook = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M2 2C2 1.44772 2.44772 1 3 1H12C12.5523 1 13 1.44772 13 2V13C13 13.5523 12.5523 14 12 14H3C2.44772 14 2 13.5523 2 13V2Z"
      stroke="currentColor"
      strokeWidth="1.5"
      fill="none"
    />
    <path d="M5 1V14" stroke="currentColor" strokeWidth="1" />
    <path d="M7 4H11" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    <path d="M7 6.5H11" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    <path d="M7 9H11" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
  </svg>
);

export const IconGraduation = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path d="M7.5 2L1 5.5L7.5 9L14 5.5L7.5 2Z" fill="currentColor" />
    <path
      d="M3 7V11C3 11 5 13 7.5 13C10 13 12 11 12 11V7"
      stroke="currentColor"
      strokeWidth="1"
      strokeLinecap="round"
    />
    <path d="M13 5.5V10" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
  </svg>
);

export const IconPalette = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M7.5 1C4.46 1 2 3.46 2 6.5C2 9.54 4.46 12 7.5 12C8.33 12 9 12.67 9 13.5C9 14.33 8.33 15 7.5 15C3.36 15 0 11.64 0 7.5C0 3.36 3.36 0 7.5 0C11.64 0 15 3.36 15 7.5C15 8.33 14.33 9 13.5 9C12.67 9 12 8.33 12 7.5C12 3.46 9.54 1 7.5 1Z"
      fill="currentColor"
    />
    <circle cx="5" cy="5" r="1.5" fill="var(--background, #fdfdfb)" />
    <circle cx="8" cy="3.5" r="1.5" fill="var(--background, #fdfdfb)" />
    <circle cx="11" cy="5.5" r="1.5" fill="var(--background, #fdfdfb)" />
    <circle cx="10.5" cy="8.5" r="1.5" fill="var(--background, #fdfdfb)" />
  </svg>
);

export const IconPlus = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path d="M7.5 2V13M2 7.5H13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

export const IconRefresh = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M1 7.5C1 3.91 3.91 1 7.5 1C10.04 1 12.23 2.47 13.26 4.58"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path
      d="M14 7.5C14 11.09 11.09 14 7.5 14C4.96 14 2.77 12.53 1.74 10.42"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path d="M11 1.5V5H14.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4 13.5V10H0.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconAlertCircle = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <circle cx="7.5" cy="7.5" r="6" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <path d="M7.5 4.5V8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="7.5" cy="10.5" r="0.75" fill="currentColor" />
  </svg>
);

export const IconHelpCircle = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <circle cx="7.5" cy="7.5" r="6" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <path
      d="M6 6C6 4.89543 6.89543 4 8 4C9.10457 4 10 4.89543 10 6C10 7.10457 9.10457 8 8 8V9"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <circle cx="8" cy="11" r="0.75" fill="currentColor" />
  </svg>
);

export const IconUpload = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M7.5 10V2M7.5 2L4 5.5M7.5 2L11 5.5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path d="M2 10V13H13V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconDownload = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M7.5 2V10M7.5 10L4 6.5M7.5 10L11 6.5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path d="M2 12V13H13V12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const IconPencil = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path d="M11 2L13 4L5 12H3V10L11 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" fill="none" />
  </svg>
);

export const IconEdit = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M10 2L13 5L5.5 12.5L1 14L2.5 9.5L10 2Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
      fill="none"
    />
  </svg>
);

export const IconGlobe = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <circle cx="7.5" cy="7.5" r="6" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <path d="M1.5 7.5H13.5" stroke="currentColor" strokeWidth="1" />
    <path d="M7.5 1.5C9.5 3.5 9.5 11.5 7.5 13.5" stroke="currentColor" strokeWidth="1" />
    <path d="M7.5 1.5C5.5 3.5 5.5 11.5 7.5 13.5" stroke="currentColor" strokeWidth="1" />
  </svg>
);

export const IconExternalLink = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M6 3H3C2.44772 3 2 3.44772 2 4V12C2 12.5523 2.44772 13 3 13H11C11.5523 13 12 12.5523 12 12V9"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path d="M8 2H13V7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M13 2L6.5 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export const IconWifi = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M1 5.5C3.5 3 6.5 2 7.5 2C8.5 2 11.5 3 14 5.5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path
      d="M3.5 8C5 6.5 6.5 5.5 7.5 5.5C8.5 5.5 10 6.5 11.5 8"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path
      d="M6 10.5C6.5 9.5 7 9 7.5 9C8 9 8.5 9.5 9 10.5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <circle cx="7.5" cy="13" r="1" fill="currentColor" />
  </svg>
);

export const IconWifiOff = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M1 5.5C3.5 3 6.5 2 7.5 2C8.5 2 11.5 3 14 5.5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path d="M2 2L13 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="7.5" cy="13" r="1" fill="currentColor" />
  </svg>
);

export const IconFileText = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M3 1C2.44772 1 2 1.44772 2 2V13C2 13.5523 2.44772 14 3 14H12C12.5523 14 13 13.5523 13 13V5L9 1H3Z"
      stroke="currentColor"
      strokeWidth="1.5"
      fill="none"
    />
    <path d="M9 1V5H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M5 7H10" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    <path d="M5 9.5H10" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    <path d="M5 12H8" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
  </svg>
);

export const IconStop = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path d="M2 2H13V13H2V2Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd" />
  </svg>
);

export const IconBan = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M7.5 0.875C3.83401 0.875 0.875 3.83401 0.875 7.5C0.875 11.166 3.83401 14.125 7.5 14.125C11.166 14.125 14.125 11.166 14.125 7.5C14.125 3.83401 11.166 0.875 7.5 0.875ZM2.125 7.5C2.125 4.52208 4.52208 2.125 7.5 2.125C8.72067 2.125 9.84463 2.53682 10.7444 3.23233L3.23233 10.7444C2.53682 9.84463 2.125 8.72067 2.125 7.5ZM4.25555 11.7677L11.7677 4.25555C12.4632 5.15537 12.875 6.27933 12.875 7.5C12.875 10.4779 10.4779 12.875 7.5 12.875C6.27933 12.875 5.15537 12.4632 4.25555 11.7677Z"
      fill="currentColor"
      fillRule="evenodd"
      clipRule="evenodd"
    />
  </svg>
);

export const IconNavigation = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path d="M7.5 1L13.5 13L7.5 10L1.5 13L7.5 1Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd" />
  </svg>
);

export const IconXCircle = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M0.877075 7.49988C0.877075 3.84219 3.84222 0.877045 7.49991 0.877045C11.1576 0.877045 14.1227 3.84219 14.1227 7.49988C14.1227 11.1576 11.1576 14.1227 7.49991 14.1227C3.84222 14.1227 0.877075 11.1576 0.877075 7.49988ZM7.49991 1.82704C4.36689 1.82704 1.82708 4.36686 1.82708 7.49988C1.82708 10.6329 4.36689 13.1727 7.49991 13.1727C10.6329 13.1727 13.1727 10.6329 13.1727 7.49988C13.1727 4.36686 10.6329 1.82704 7.49991 1.82704ZM9.85358 5.14644C10.0488 5.3417 10.0488 5.65829 9.85358 5.85355L8.20711 7.5L9.85358 9.14644C10.0488 9.3417 10.0488 9.65829 9.85358 9.85355C9.65832 10.0488 9.34174 10.0488 9.14648 9.85355L7.50001 8.20711L5.85358 9.85355C5.65832 10.0488 5.34174 10.0488 5.14648 9.85355C4.95122 9.65829 4.95122 9.3417 5.14648 9.14644L6.79291 7.5L5.14648 5.85355C4.95122 5.65829 4.95122 5.3417 5.14648 5.14644C5.34174 4.95118 5.65832 4.95118 5.85358 5.14644L7.50001 6.79289L9.14648 5.14644C9.34174 4.95118 9.65832 4.95118 9.85358 5.14644Z"
      fill="currentColor"
      fillRule="evenodd"
      clipRule="evenodd"
    />
  </svg>
);

export const IconSearch = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M10 6.5C10 8.433 8.433 10 6.5 10C4.567 10 3 8.433 3 6.5C3 4.567 4.567 3 6.5 3C8.433 3 10 4.567 10 6.5ZM9.30884 10.0159C8.53901 10.6318 7.56251 11 6.5 11C4.01472 11 2 8.98528 2 6.5C2 4.01472 4.01472 2 6.5 2C8.98528 2 11 4.01472 11 6.5C11 7.56251 10.6318 8.53901 10.0159 9.30884L12.8536 12.1464C13.0488 12.3417 13.0488 12.6583 12.8536 12.8536C12.6583 13.0488 12.3417 13.0488 12.1464 12.8536L9.30884 10.0159Z"
      fill="currentColor"
      fillRule="evenodd"
      clipRule="evenodd"
    />
  </svg>
);

export const IconSave = ({ className }: IconProps) => (
  <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <path
      d="M3 1.5C2.44772 1.5 2 1.94772 2 2.5V12.5C2 13.0523 2.44772 13.5 3 13.5H12C12.5523 13.5 13 13.0523 13 12.5V4.5L10 1.5H3ZM3 2.5H9.5V4.5H2.5V2.5C2.5 2.22386 2.72386 2 3 2ZM2.5 5.5H10.5V12.5C10.5 12.7761 10.2761 13 10 13H3C2.72386 13 2.5 12.7761 2.5 12.5V5.5ZM5 2.5V4H8V2.5H5ZM4.5 8.5C4.5 8.22386 4.72386 8 5 8H10C10.2761 8 10.5 8.22386 10.5 8.5C10.5 8.77614 10.2761 9 10 9H5C4.72386 9 4.5 8.77614 4.5 8.5ZM5 10.5C4.72386 10.5 4.5 10.7239 4.5 11C4.5 11.2761 4.72386 11.5 5 11.5H10C10.2761 11.5 10.5 11.2761 10.5 11C10.5 10.7239 10.2761 10.5 10 10.5H5Z"
      fill="currentColor"
      fillRule="evenodd"
      clipRule="evenodd"
    />
  </svg>
);
