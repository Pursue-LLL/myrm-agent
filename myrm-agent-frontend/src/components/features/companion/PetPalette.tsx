'use client';

/**
 * PetPalette — session-scoped Petdex picker (GUI equivalent of Hermes /pet list).
 *
 * [INPUT]
 * - @/store/useCompanionStore (POS: 伴侣全局状态 — palette 开关与精灵配置)
 * - @/components/features/companion/PetGallery (POS: Petdex 图鉴安装网格)
 * - @/hooks/ui/useMediaQuery::useIsMobile (POS: 响应式断点检测)
 *
 * [OUTPUT]
 * - PetPalette: Dialog (desktop) / Sheet (mobile) with active pet summary + gallery
 *
 * [POS]
 * Opened via /pet slash or command palette; mounted from ChatWindowSatellites.
 */

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';

import PetGallery from '@/components/features/companion/PetGallery';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { useIsMobile } from '@/hooks/ui/useMediaQuery';
import useCompanionStore from '@/store/useCompanionStore';

function PetPaletteBody({ paletteOpen }: { paletteOpen: boolean }) {
  const t = useTranslations('companion');
  const spriteEnabled = useCompanionStore((s) => s.spriteEnabled);
  const spriteConfig = useCompanionStore((s) => s.spriteConfig);
  const setSpriteEnabled = useCompanionStore((s) => s.setSpriteEnabled);
  const saveConfigToServer = useCompanionStore((s) => s.saveConfigToServer);

  const handleToggleOverlay = useCallback(
    (enabled: boolean) => {
      setSpriteEnabled(enabled);
      void saveConfigToServer();
    },
    [setSpriteEnabled, saveConfigToServer],
  );

  const activeName = spriteConfig?.displayName ?? spriteConfig?.petSlug;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">{t('sprite.activePet')}</p>
            <p className="text-sm font-medium truncate">
              {activeName ?? t('sprite.activePetEmpty')}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Label htmlFor="pet-palette-overlay" className="text-xs text-muted-foreground">
              {t('sprite.enableLabel')}
            </Label>
            <Switch
              id="pet-palette-overlay"
              checked={spriteEnabled}
              onCheckedChange={handleToggleOverlay}
              disabled={!spriteConfig}
            />
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground leading-snug">{t('palette.hint')}</p>
      </div>

      <PetGallery reloadInstalledWhen={paletteOpen} />
    </div>
  );
}

export default function PetPalette() {
  const t = useTranslations('companion');
  const isMobile = useIsMobile();
  const open = useCompanionStore((s) => s.petPaletteOpen);
  const setPetPaletteOpen = useCompanionStore((s) => s.setPetPaletteOpen);

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={setPetPaletteOpen}>
        <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto rounded-t-xl px-4 pb-6">
          <SheetHeader className="text-left pb-2">
            <SheetTitle>{t('palette.title')}</SheetTitle>
          </SheetHeader>
          <PetPaletteBody paletteOpen={open} />
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <Dialog open={open} onOpenChange={setPetPaletteOpen}>
      <DialogContent className="max-w-md" data-testid="pet-palette-dialog">
        <DialogHeader>
          <DialogTitle>{t('palette.title')}</DialogTitle>
        </DialogHeader>
        <PetPaletteBody paletteOpen={open} />
      </DialogContent>
    </Dialog>
  );
}
