/**
 * [INPUT]
 * - @/lib/desktop-bridge::getDesktopWindowControlsState, DesktopWindowControlsState
 *
 * [OUTPUT]
 * - useWindowControls: Hook providing reactive window controls insets and platform info
 *
 * [POS]
 * Responsive window controls state hook for adapting macOS traffic lights and custom titlebars.
 */

import { useState, useEffect } from 'react';
import { getDesktopWindowControlsState, type DesktopWindowControlsState } from '@/lib/desktop-bridge';

export function useWindowControls(): DesktopWindowControlsState {
  const [state, setState] = useState<DesktopWindowControlsState>(() => getDesktopWindowControlsState());

  useEffect(() => {
    // Initial sync
    setState(getDesktopWindowControlsState());
  }, []);

  return state;
}
