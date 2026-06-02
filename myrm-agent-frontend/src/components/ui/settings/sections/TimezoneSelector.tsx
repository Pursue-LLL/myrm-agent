'use client';

import { memo, useState, useEffect, useMemo, useRef } from 'react';
import { IconSearch, IconGlobe, IconCheck, IconChevronDown } from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

function getUtcOffset(tz: string): string {
  try {
    const now = new Date();
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'shortOffset',
    });
    const parts = formatter.formatToParts(now);
    const offset = parts.find((p) => p.type === 'timeZoneName')?.value ?? '';
    return offset.replace('GMT', 'UTC');
  } catch {
    return '';
  }
}

const ALL_TIMEZONES: string[] = (() => {
  try {
    return Intl.supportedValuesOf('timeZone');
  } catch {
    return [
      'UTC',
      'Asia/Shanghai',
      'Asia/Tokyo',
      'Asia/Seoul',
      'Asia/Singapore',
      'Asia/Kolkata',
      'Asia/Dubai',
      'Europe/London',
      'Europe/Paris',
      'Europe/Berlin',
      'Europe/Moscow',
      'America/New_York',
      'America/Chicago',
      'America/Denver',
      'America/Los_Angeles',
      'America/Sao_Paulo',
      'Australia/Sydney',
      'Pacific/Auckland',
    ];
  }
})();

const POPULAR_TIMEZONES = new Set([
  'UTC',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Seoul',
  'Asia/Singapore',
  'Asia/Kolkata',
  'Asia/Dubai',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Moscow',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Sao_Paulo',
  'Australia/Sydney',
  'Pacific/Auckland',
]);

const TimezoneSelector = memo<{ value: string; onChange: (tz: string) => void }>(({ value, onChange }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    if (!q) {
      const popular = ALL_TIMEZONES.filter((tz) => POPULAR_TIMEZONES.has(tz));
      const rest = ALL_TIMEZONES.filter((tz) => !POPULAR_TIMEZONES.has(tz));
      return { popular, rest };
    }
    const matches = ALL_TIMEZONES.filter(
      (tz) => tz.toLowerCase().includes(q) || getUtcOffset(tz).toLowerCase().includes(q),
    );
    return { popular: [], rest: matches };
  }, [search]);

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (listRef.current && !listRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleSelect = (tz: string) => {
    onChange(tz);
    setOpen(false);
    setSearch('');
  };

  const offset = getUtcOffset(value);

  const renderItem = (tz: string) => (
    <button
      key={tz}
      onClick={() => handleSelect(tz)}
      className={cn(
        'w-full flex items-center justify-between px-3 py-2 text-sm rounded-full transition-colors',
        tz === value ? 'bg-primary/10 text-primary' : 'hover:bg-accent text-foreground',
      )}
    >
      <span className="truncate">{tz.replace(/_/g, ' ')}</span>
      <span className="flex items-center gap-2 shrink-0 ml-2">
        <span className="text-xs text-muted-foreground font-mono">{getUtcOffset(tz)}</span>
        {tz === value && <IconCheck className="w-3.5 h-3.5 text-primary" />}
      </span>
    </button>
  );

  return (
    <div className="relative" ref={listRef}>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'w-full flex items-center justify-between px-4 py-2.5 rounded-lg',
          'bg-accent/30 border border-border/50',
          'text-sm text-foreground',
          'hover:border-border transition-all duration-200',
          open && 'ring-2 ring-primary/20 border-primary/50',
        )}
      >
        <span className="flex items-center gap-2 truncate">
          <IconGlobe className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <span className="truncate">{value.replace(/_/g, ' ')}</span>
          <span className="text-xs text-muted-foreground font-mono shrink-0">{offset}</span>
        </span>
        <IconChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0 ml-2" />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border bg-popover shadow-lg overflow-hidden">
          <div className="p-2 border-b">
            <div className="relative">
              <IconSearch className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                ref={inputRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search..."
                className="w-full pl-8 pr-3 py-1.5 text-sm bg-transparent outline-none placeholder:text-muted-foreground/50"
              />
            </div>
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            {filtered.popular.length > 0 && (
              <>
                <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                  Popular
                </p>
                {filtered.popular.map(renderItem)}
                {filtered.rest.length > 0 && <div className="my-1 border-t border-border/30" />}
              </>
            )}
            {filtered.rest.map(renderItem)}
            {filtered.popular.length === 0 && filtered.rest.length === 0 && (
              <p className="px-3 py-4 text-sm text-center text-muted-foreground">No results</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
});
TimezoneSelector.displayName = 'TimezoneSelector';

export default TimezoneSelector;
