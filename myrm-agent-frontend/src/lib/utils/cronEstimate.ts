// Cron expression estimation utilities.
// Provides functions to estimate the number of executions per month
// for different schedule types (cron, interval, once).

// Average days per month (365.25 / 12)
const AVG_DAYS_PER_MONTH = 30.4375;

// Hours per day
const HOURS_PER_DAY = 24;

// Minutes per hour
const MINUTES_PER_HOUR = 60;

// Estimate monthly executions for a cron expression.
// Supports common patterns like every minute, every N minutes, every hour, etc.
// For complex expressions, returns a rough estimate based on the minute and hour fields.
export function estimateCronMonthlyExecutions(expr: string): number | null {
  const parts = expr.trim().split(/\s+/);
  if (parts.length < 5) return null;

  const [minuteField, hourField] = parts;

  // Parse minute field
  const minuteMultiplier = parseFieldMultiplier(minuteField, 60);
  if (minuteMultiplier === null) return null;

  // Parse hour field
  const hourMultiplier = parseFieldMultiplier(hourField, 24);
  if (hourMultiplier === null) return null;

  // Calculate executions per day
  // minuteMultiplier: how many minutes between executions (e.g., 5 for */5)
  // hourMultiplier: how many hours between executions (e.g., 2 for */2)
  const executionsPerDay = (MINUTES_PER_HOUR / minuteMultiplier) * (HOURS_PER_DAY / hourMultiplier);

  // Calculate monthly executions
  return Math.round(executionsPerDay * AVG_DAYS_PER_MONTH);
}

// Estimate monthly executions for an interval schedule.
// intervalMs: Interval in milliseconds
export function estimateIntervalMonthlyExecutions(intervalMs: number): number | null {
  if (intervalMs <= 0) return null;

  const millisecondsPerMonth = AVG_DAYS_PER_MONTH * HOURS_PER_DAY * MINUTES_PER_HOUR * 60 * 1000;
  return Math.round(millisecondsPerMonth / intervalMs);
}

// Parse a cron field and return the multiplier.
// Handles wildcard (*), step (*/N), comma-separated values (N,M,O), and single values.
// Returns null if the field cannot be parsed.
function parseFieldMultiplier(field: string, maxValue: number): number | null {
  // Wildcard: every unit
  if (field === '*') return 1;

  // Step: */N or N/M
  const stepMatch = field.match(/^\*\/(\d+)$/);
  if (stepMatch) {
    const step = parseInt(stepMatch[1], 10);
    return step > 0 ? step : null;
  }

  // Specific values: N,M,O
  if (field.includes(',')) {
    const values = field.split(',').filter((v) => v.trim() !== '');
    return values.length > 0 ? maxValue / values.length : null;
  }

  // Single value
  const num = parseInt(field, 10);
  if (!isNaN(num) && num >= 0 && num < maxValue) {
    return maxValue; // Specific time = once per period
  }

  return null;
}

// Format monthly execution count for display.
// Returns a human-readable string like "~288 times/month" or "~1,440 times/month".
export function formatMonthlyExecutions(count: number): string {
  if (count <= 0) return '0 times/month';
  if (count === 1) return '1 time/month';

  // Format with locale-appropriate number formatting
  const formatted = count.toLocaleString();
  return `~${formatted} times/month`;
}

// Get a risk level indicator for the execution frequency.
// Returns 'low', 'medium', or 'high' based on monthly executions.
export function getFrequencyRiskLevel(monthlyExecutions: number): 'low' | 'medium' | 'high' {
  if (monthlyExecutions <= 30) return 'low'; // ~once/day
  if (monthlyExecutions <= 720) return 'medium'; // ~once/hour
  return 'high'; // more than once/hour
}
