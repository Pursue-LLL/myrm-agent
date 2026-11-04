import { describe, expect, it } from 'vitest';

import { weekdayLabels } from '../weekdayLabels';

describe('weekdayLabels', () => {
  it('returns seven names that start on Monday', () => {
    expect(weekdayLabels('en')).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
  });

  it('follows the language of the interface', () => {
    expect(weekdayLabels('zh')).toEqual(['周一', '周二', '周三', '周四', '周五', '周六', '周日']);
    expect(weekdayLabels('ja')[0]).toBe('月');
    expect(weekdayLabels('de')[0]).toMatch(/^Mo/);
    expect(weekdayLabels('ko')[6]).toBe('일');
  });

  it('keeps Traditional Chinese distinct from Simplified Chinese', () => {
    expect(weekdayLabels('zh-TW')[0]).toBe('週一');
  });
});
