/**
 * 智能体画廊背景效果组件
 */

export const GalleryBackground = () => {
  return (
    <div
      className="absolute pointer-events-none"
      style={{
        inset: '-20px -30px -15px -30px',
        zIndex: 0,
      }}
    >
      <svg
        className="w-full h-full"
        viewBox="0 0 500 200"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="presetInkGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#f3e8ff" stopOpacity="0.5" />
            <stop offset="30%" stopColor="#ede9fe" stopOpacity="0.6" />
            <stop offset="60%" stopColor="#faf5ff" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#f3e8ff" stopOpacity="0.4" />
          </linearGradient>
          <filter id="presetInkBlur" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <path
          d="M35,40
             C80,15 140,25 200,20
             C280,14 350,28 420,24
             C465,21 490,50 480,90
             C485,130 475,165 445,185
             C390,200 300,195 200,190
             C110,188 45,180 20,155
             C5,130 10,85 35,40 Z"
          fill="url(#presetInkGradient)"
          filter="url(#presetInkBlur)"
        />

        <ellipse cx="470" cy="50" rx="18" ry="12" fill="#ede9fe" fillOpacity="0.4" />
        <ellipse cx="25" cy="160" rx="15" ry="10" fill="#faf5ff" fillOpacity="0.4" />
        <circle cx="480" cy="130" r="12" fill="#f3e8ff" fillOpacity="0.35" />
      </svg>
    </div>
  );
};
