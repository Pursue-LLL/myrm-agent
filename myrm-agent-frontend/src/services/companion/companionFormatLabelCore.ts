/**
 * [INPUT]
 * - InstalledCompanionPet format_tier / format_label from GET /companion/pets
 *
 * [OUTPUT]
 * - resolveCompanionFormatLabelKey: i18n key under companion.gallery for format chip
 *
 * [POS]
 * Pure helper so InstalledPetRow can localize server-side English atlas labels.
 */

import type { InstalledCompanionPet } from '@/services/companion/petInstall';

export function resolveCompanionFormatLabelKey(
  pet: Pick<InstalledCompanionPet, 'format_tier' | 'format_label'>,
): string | null {
  const tier = pet.format_tier?.trim();
  if (!tier) {return null;}
  if (tier === 'warn') {return 'gallery.formatNonStandard';}
  if (tier === 'fail') {return 'gallery.formatInvalid';}
  const label = pet.format_label?.toLowerCase() ?? '';
  if (label.includes('legacy')) {return 'gallery.formatLegacyStandard';}
  return 'gallery.formatCodexStandard';
}
