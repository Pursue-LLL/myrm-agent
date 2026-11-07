/**
 * [INPUT]
 * - ../composer-options/useComposerOptionsOpen::useComposerOptionsOpen (POS: 选项区开合的本机记忆)
 *
 * [OUTPUT]
 * - useComposerPanels: 手机操作表、单轮能力弹层与桌面选项区的开合状态及其联动。
 *
 * [POS]
 * 三块可开合面板互相牵动：手机没有选项区，所以能力编辑落在操作表；桌面上能力弹层锚在选项区内的控件上，
 * 编辑时选项区要临时展开，又不能改写用户已存的开合选择。联动集中在这里，调用方只拿到结果。
 */
import { useCallback, useId, useState } from 'react';

import { useComposerOptionsOpen } from '../composer-options/useComposerOptionsOpen';

/** Tailwind's `sm` breakpoint: from here the desktop row and options region replace the phone's "+" action sheet. */
const DESKTOP_COMPOSER_QUERY = '(min-width: 640px)';

export function useComposerPanels() {
  const [isMobileSheetOpen, setIsMobileSheetOpen] = useState(false);
  const [isTurnCapabilityOpen, setIsTurnCapabilityOpen] = useState(false);
  const optionsRegionId = useId();
  const [optionsOpen, setOptionsOpen] = useComposerOptionsOpen();

  const openMobileSheet = useCallback(() => setIsMobileSheetOpen(true), []);
  const closeMobileSheet = useCallback(() => setIsMobileSheetOpen(false), []);

  const openCapabilityEditor = useCallback(() => {
    // The desktop edits in the options region's popover; the phone hides that region and edits in the action sheet.
    if (window.matchMedia(DESKTOP_COMPOSER_QUERY).matches) {
      setIsTurnCapabilityOpen(true);
    } else {
      setIsMobileSheetOpen(true);
    }
  }, []);

  // The capability popover anchors on a control inside the region, so editing capabilities shows the region
  // without changing the viewer's saved choice.
  const optionsExpanded = optionsOpen || isTurnCapabilityOpen;
  const toggleOptions = useCallback(() => {
    setIsTurnCapabilityOpen(false);
    setOptionsOpen(!optionsExpanded);
  }, [optionsExpanded, setOptionsOpen]);

  return {
    isMobileSheetOpen,
    openMobileSheet,
    closeMobileSheet,
    isTurnCapabilityOpen,
    setIsTurnCapabilityOpen,
    openCapabilityEditor,
    optionsRegionId,
    optionsExpanded,
    toggleOptions,
  };
}
