import { describe, expect, it } from 'vitest';

import { localizeDoctorCheckMessage } from '@/services/companion/companionDoctorCheckI18nCore';
import type { CompanionDoctorCheck } from '@/services/companion/petDoctor';

describe('localizeDoctorCheckMessage', () => {
  const t = (key: string, values?: Record<string, string | number>) => {
    const map: Record<string, string> = {
      'doctor.serverChecks.config_sprite_slug.fail': 'No active pet is selected.',
      'doctor.serverChecks.config_sprite_slug.pass': 'Active pet is {slug}.',
      'doctor.serverChecks.disk_installed_pets.pass': '{count} pet(s) installed.',
    };
    let out = map[key] ?? key;
    if (values) {
      for (const [k, v] of Object.entries(values)) {
        out = out.replace(`{${k}}`, String(v));
      }
    }
    return out;
  };

  it('localizes known check id', () => {
    const check: CompanionDoctorCheck = {
      id: 'config.sprite.slug',
      status: 'fail',
      message: 'No active pet slug in companion config.',
      fixAction: 'open_pet_gallery',
    };
    expect(localizeDoctorCheckMessage(t, check, {})).toBe('No active pet is selected.');
  });

  it('interpolates slug for pass check', () => {
    const check: CompanionDoctorCheck = {
      id: 'config.sprite.slug',
      status: 'pass',
      message: 'ignored',
      fixAction: null,
    };
    expect(localizeDoctorCheckMessage(t, check, { activeSlug: 'nous-girl' })).toBe('Active pet is nous-girl.');
  });

  it('falls back to server message when key missing', () => {
    const check: CompanionDoctorCheck = {
      id: 'atlas.format',
      status: 'fail',
      message: 'spritesheet not found: /tmp/x.webp',
      fixAction: 'open_pet_gallery',
    };
    expect(localizeDoctorCheckMessage(t, check, {})).toBe('spritesheet not found: /tmp/x.webp');
  });
});
