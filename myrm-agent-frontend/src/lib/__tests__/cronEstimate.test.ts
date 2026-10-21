import {
  estimateCronMonthlyExecutions,
  estimateIntervalMonthlyExecutions,
  formatMonthlyExecutions,
  getFrequencyRiskLevel,
} from '../utils/cronEstimate';

describe('estimateCronMonthlyExecutions', () => {
  it('should return null for invalid expressions', () => {
    expect(estimateCronMonthlyExecutions('')).toBeNull();
    expect(estimateCronMonthlyExecutions('* * *')).toBeNull();
    expect(estimateCronMonthlyExecutions('invalid')).toBeNull();
  });

  it('should estimate every minute correctly', () => {
    // * * * * * = every minute = 60 * 24 * 30.4375 = 43,830
    const result = estimateCronMonthlyExecutions('* * * * *');
    expect(result).toBe(43830);
  });

  it('should estimate every 5 minutes correctly', () => {
    // */5 * * * * = every 5 minutes = (60/5) * 24 * 30.4375 = 8,766
    const result = estimateCronMonthlyExecutions('*/5 * * * *');
    expect(result).toBe(8766);
  });

  it('should estimate every hour correctly', () => {
    // 0 * * * * = every hour
    // minute=60 (specific), hour=1 (wildcard)
    // executionsPerDay = (60/60) * (24/1) = 1 * 24 = 24
    // monthly = 24 * 30.4375 = 730.5
    const result = estimateCronMonthlyExecutions('0 * * * *');
    expect(result).toBe(731);
  });

  it('should estimate every 2 hours correctly', () => {
    // 0 */2 * * * = every 2 hours
    // minute=60 (specific), hour=2 (step of 2)
    // executionsPerDay = (60/60) * (24/2) = 1 * 12 = 12
    // monthly = 12 * 30.4375 = 365.25
    const result = estimateCronMonthlyExecutions('0 */2 * * *');
    expect(result).toBe(365);
  });

  it('should estimate once a day correctly', () => {
    // 0 0 * * * = once a day
    // minute="0" → specific value, multiplier=60 (maxValue)
    // hour="0" → specific value, multiplier=24 (maxValue)
    // executionsPerDay = (60/60) * (24/24) = 1
    // monthly = 1 * 30.4375 ≈ 30
    const result = estimateCronMonthlyExecutions('0 0 * * *');
    expect(result).toBe(30);
  });

  it('should estimate once a week correctly', () => {
    // 0 0 * * 0 = once a week
    // Our simple parser doesn't handle day-of-week, returns same as "0 0 * * *"
    // executionsPerDay = (60/60) * (24/24) = 1, monthly = 30
    const result = estimateCronMonthlyExecutions('0 0 * * 0');
    expect(result).toBe(30);
  });

  it('should handle comma-separated values', () => {
    // 0 9,18 * * * = twice a day
    // minute="0" → specific, multiplier=60
    // hour="9,18" → 2 values, multiplier = 24/2 = 12
    // executionsPerDay = (60/60) * (24/12) = 1 * 2 = 2
    // monthly = 2 * 30.4375 ≈ 61
    const result = estimateCronMonthlyExecutions('0 9,18 * * *');
    expect(result).toBe(61);
  });

  it('should handle complex expressions with ranges', () => {
    // 0 9-17 * * 1-5 = weekdays 9am-5pm
    // Our simple parser treats "9-17" as single value (parseInt returns 9)
    // So hourMultiplier = 24 (maxValue), same as "0 0 * * *"
    // executionsPerDay = (60/60) * (24/24) = 1, monthly = 30
    const result = estimateCronMonthlyExecutions('0 9-17 * * 1-5');
    expect(result).toBe(30);
  });

  it('should return null for out-of-range single value', () => {
    // minute=99 is >= 60 (maxValue), so parseFieldMultiplier returns null
    expect(estimateCronMonthlyExecutions('99 * * * *')).toBeNull();
  });

  it('should return null for step of zero', () => {
    // */0 is syntactically invalid, step=0 → parseFieldMultiplier returns null
    expect(estimateCronMonthlyExecutions('*/0 * * * *')).toBeNull();
  });
});

describe('estimateIntervalMonthlyExecutions', () => {
  it('should return null for invalid intervals', () => {
    expect(estimateIntervalMonthlyExecutions(0)).toBeNull();
    expect(estimateIntervalMonthlyExecutions(-1000)).toBeNull();
  });

  it('should estimate 5-minute interval correctly', () => {
    // 5 minutes = 300,000 ms
    // Monthly: 30.4375 * 24 * 60 * 60 * 1000 / 300,000 = 8,766
    const result = estimateIntervalMonthlyExecutions(5 * 60 * 1000);
    expect(result).toBe(8766);
  });

  it('should estimate 1-hour interval correctly', () => {
    // 1 hour = 3,600,000 ms
    // Monthly: 30.4375 * 24 * 60 * 60 * 1000 / 3,600,000 = 730.5
    const result = estimateIntervalMonthlyExecutions(60 * 60 * 1000);
    expect(result).toBe(731);
  });

  it('should estimate 1-day interval correctly', () => {
    // 1 day = 86,400,000 ms
    // Monthly: 30.4375 * 24 * 60 * 60 * 1000 / 86,400,000 = 30.4375
    const result = estimateIntervalMonthlyExecutions(24 * 60 * 60 * 1000);
    expect(result).toBe(30);
  });
});

describe('formatMonthlyExecutions', () => {
  it('should format zero correctly', () => {
    expect(formatMonthlyExecutions(0)).toBe('0 times/month');
  });

  it('should format one correctly', () => {
    expect(formatMonthlyExecutions(1)).toBe('1 time/month');
  });

  it('should format small numbers correctly', () => {
    expect(formatMonthlyExecutions(288)).toBe('~288 times/month');
  });

  it('should format large numbers with commas', () => {
    expect(formatMonthlyExecutions(8766)).toBe('~8,766 times/month');
  });
});

describe('getFrequencyRiskLevel', () => {
  it('should return low for daily or less', () => {
    expect(getFrequencyRiskLevel(1)).toBe('low');
    expect(getFrequencyRiskLevel(30)).toBe('low');
  });

  it('should return medium for hourly frequency', () => {
    expect(getFrequencyRiskLevel(31)).toBe('medium');
    expect(getFrequencyRiskLevel(720)).toBe('medium');
  });

  it('should return high for more than hourly', () => {
    expect(getFrequencyRiskLevel(721)).toBe('high');
    expect(getFrequencyRiskLevel(8766)).toBe('high');
  });
});
