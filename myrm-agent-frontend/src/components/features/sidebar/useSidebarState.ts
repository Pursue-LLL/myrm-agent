import { useState, useEffect, useRef } from 'react';
import { DRAG_CONFIG } from './constants';

export const useSidebarState = () => {
  const [isPinned, setIsPinned] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [isScrolling, setIsScrolling] = useState(false);

  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 检测移动端
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 1024);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // 滚动检测
  useEffect(() => {
    if (!isMobile) return;

    const handleScroll = () => {
      setIsScrolling(true);
      if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
      scrollTimeoutRef.current = setTimeout(() => setIsScrolling(false), DRAG_CONFIG.SCROLL_DELAY);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    };
  }, [isMobile]);

  // 设置CSS自定义属性
  const isExpanded = isPinned || isHovered;
  useEffect(() => {
    const width = isMobile ? (isMobileOpen ? '90vw' : '0px') : isExpanded ? '320px' : '80px';
    document.documentElement.style.setProperty('--sidebar-width', width);
  }, [isExpanded, isMobile, isMobileOpen]);

  return {
    isPinned,
    setIsPinned,
    isHovered,
    setIsHovered,
    isMobileOpen,
    setIsMobileOpen,
    isMobile,
    isScrolling,
    isExpanded,
  };
};
