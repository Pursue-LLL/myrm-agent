import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { createElement } from 'react';

import {
  SPECIES_ICON_MAP,
  HAT_ICON_MAP,
  IconCat,
  IconDog,
  IconBear,
  IconRabbit,
  IconOwl,
  IconDragon,
  IconSloth,
  IconPenguin,
  IconFox,
  IconOctopus,
  IconCactus,
  IconRobot,
  IconMushroom,
  IconPanda,
  IconFrog,
  HatCrown,
  HatTophat,
  HatStar,
  HatWizard,
  HatBow,
  HatFlower,
  HatFire,
  HatIce,
  HatGrad,
} from '../CompanionIcons';
import { HATS, SPECIES } from '../companionGenerator';

describe('CompanionIcons', () => {
  describe('SPECIES_ICON_MAP', () => {
    it('has an SVG component for every species', () => {
      for (const species of SPECIES) {
        const icon = SPECIES_ICON_MAP[species];
        expect(icon, `Missing SVG icon for species: ${species}`).toBeDefined();
        expect(typeof icon).toBe('function');
      }
    });

    it('has exactly the same count as SPECIES', () => {
      expect(Object.keys(SPECIES_ICON_MAP).length).toBe(SPECIES.length);
    });
  });

  describe('HAT_ICON_MAP', () => {
    it('has an SVG component for every hat', () => {
      for (const hat of HATS) {
        const icon = HAT_ICON_MAP[hat];
        expect(icon, `Missing SVG icon for hat: ${hat}`).toBeDefined();
        expect(typeof icon).toBe('function');
      }
    });

    it('has exactly the same count as HATS', () => {
      expect(Object.keys(HAT_ICON_MAP).length).toBe(HATS.length);
    });
  });

  describe('lookup correctness', () => {
    it('returns undefined for unknown emoji', () => {
      expect(SPECIES_ICON_MAP['🦄']).toBeUndefined();
      expect(HAT_ICON_MAP['🦄']).toBeUndefined();
    });
  });

  describe('species SVG rendering', () => {
    const speciesIcons = [
      IconCat,
      IconDog,
      IconBear,
      IconRabbit,
      IconOwl,
      IconDragon,
      IconSloth,
      IconPenguin,
      IconFox,
      IconOctopus,
      IconCactus,
      IconRobot,
      IconMushroom,
      IconPanda,
      IconFrog,
    ];

    it.each(speciesIcons.map((Icon, i) => [SPECIES[i], Icon] as const))(
      'renders %s species SVG without error',
      (_emoji, Icon) => {
        const { container } = render(createElement(Icon, { size: 32 }));
        const svg = container.querySelector('svg');
        expect(svg).not.toBeNull();
        expect(svg!.getAttribute('width')).toBe('32');
        expect(svg!.getAttribute('height')).toBe('32');
      },
    );
  });

  describe('hat SVG rendering', () => {
    const hatIcons = [HatCrown, HatTophat, HatStar, HatWizard, HatBow, HatFlower, HatFire, HatIce, HatGrad];

    it.each(hatIcons.map((Icon, i) => [HATS[i], Icon] as const))('renders %s hat SVG without error', (_emoji, Icon) => {
      const { container } = render(createElement(Icon, { size: 16 }));
      const svg = container.querySelector('svg');
      expect(svg).not.toBeNull();
    });
  });

  describe('custom size prop', () => {
    it('passes custom size to species icon', () => {
      const { container } = render(createElement(IconCat, { size: 64 }));
      const svg = container.querySelector('svg')!;
      expect(svg.getAttribute('width')).toBe('64');
      expect(svg.getAttribute('height')).toBe('64');
    });

    it('uses default size 24 for species icons', () => {
      const { container } = render(createElement(IconCat));
      const svg = container.querySelector('svg')!;
      expect(svg.getAttribute('width')).toBe('24');
    });

    it('uses default size 12 for hat icons', () => {
      const { container } = render(createElement(HatCrown));
      const svg = container.querySelector('svg')!;
      expect(svg.getAttribute('width')).toBe('12');
    });
  });
});
