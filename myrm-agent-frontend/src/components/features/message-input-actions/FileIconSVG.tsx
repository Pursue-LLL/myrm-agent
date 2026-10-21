import React from 'react';

export const FileIconSVG = ({ extension, className }: { extension: string; className?: string }) => {
  // A sleek, premium SVG icon generator based on file extension
  // No Lucide, no emojis.

  const getColors = () => {
    switch (extension.toLowerCase()) {
      case 'ts':
      case 'tsx':
        return {
          bg: 'fill-blue-500/10 dark:fill-blue-400/10',
          stroke: 'stroke-blue-600 dark:stroke-blue-400',
          text: 'fill-blue-700 dark:fill-blue-300',
        };
      case 'js':
      case 'jsx':
        return {
          bg: 'fill-yellow-500/10 dark:fill-yellow-400/10',
          stroke: 'stroke-yellow-600 dark:stroke-yellow-400',
          text: 'fill-yellow-700 dark:fill-yellow-300',
        };
      case 'py':
        return {
          bg: 'fill-emerald-500/10 dark:fill-emerald-400/10',
          stroke: 'stroke-emerald-600 dark:stroke-emerald-400',
          text: 'fill-emerald-700 dark:fill-emerald-300',
        };
      case 'json':
        return {
          bg: 'fill-orange-500/10 dark:fill-orange-400/10',
          stroke: 'stroke-orange-600 dark:stroke-orange-400',
          text: 'fill-orange-700 dark:fill-orange-300',
        };
      case 'md':
      case 'mdx':
        return {
          bg: 'fill-slate-500/10 dark:fill-slate-400/10',
          stroke: 'stroke-slate-600 dark:stroke-slate-400',
          text: 'fill-slate-700 dark:fill-slate-300',
        };
      case 'css':
      case 'scss':
        return {
          bg: 'fill-pink-500/10 dark:fill-pink-400/10',
          stroke: 'stroke-pink-600 dark:stroke-pink-400',
          text: 'fill-pink-700 dark:fill-pink-300',
        };
      case 'html':
        return {
          bg: 'fill-red-500/10 dark:fill-red-400/10',
          stroke: 'stroke-red-600 dark:stroke-red-400',
          text: 'fill-red-700 dark:fill-red-300',
        };
      default:
        return {
          bg: 'fill-gray-500/10 dark:fill-gray-400/10',
          stroke: 'stroke-gray-500 dark:stroke-gray-400',
          text: 'fill-gray-600 dark:fill-gray-300',
        };
    }
  };

  const colors = getColors();
  const extText = extension.substring(0, 3).toUpperCase();

  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
      <path
        d="M14 2H6C4.89543 2 4 2.89543 4 4V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V8L14 2Z"
        className={`${colors.bg} ${colors.stroke}`}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M14 2V8H20" className={colors.stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <text
        x="12"
        y="16"
        fontSize="5"
        fontWeight="700"
        textAnchor="middle"
        className={colors.text}
        fontFamily="monospace"
      >
        {extText}
      </text>
    </svg>
  );
};
