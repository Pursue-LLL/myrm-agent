'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconShield,
  IconChevronDown,
  IconCheck,
  IconLoader,
  IconLock,
  IconFolder,
  IconZap,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { toast } from '@/lib/utils/toast';
import { fetchWithTimeout } from '@/lib/api';

interface SecurityProfile {
  id: string;
  profile_key: string;
  display_name: string;
  description: string | null;
  config_json: Record<string, unknown>;
  is_builtin: boolean;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

interface ProfileListResponse {
  profiles: SecurityProfile[];
  active_key: string | null;
}

const PROFILE_ICONS: Record<string, typeof IconShield> = {
  readonly: IconLock,
  workspace: IconFolder,
  full_access: IconZap,
};

const SecurityProfileSelector = memo(function SecurityProfileSelector({
  onProfileSelect,
}: {
  onProfileSelect?: (profile: SecurityProfile) => void;
}) {
  const t = useTranslations('settings.securityPolicy');
  const [profiles, setProfiles] = useState<SecurityProfile[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activating, setActivating] = useState<string | null>(null);

  const fetchProfiles = useCallback(async () => {
    try {
      const res = await fetchWithTimeout('/security/profiles', { method: 'GET' }, 10_000);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ProfileListResponse = await res.json();
      setProfiles(data.profiles);
      setActiveKey(data.active_key);
    } catch (err) {
      console.error('Failed to load security profiles:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  const handleActivate = useCallback(
    async (profileKey: string) => {
      setActivating(profileKey);
      try {
        const res = await fetchWithTimeout(`/security/profiles/${profileKey}/activate`, { method: 'POST' }, 10_000);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const activated: SecurityProfile = await res.json();
        setActiveKey(activated.profile_key);
        toast.success(`Activated profile: ${activated.display_name}`);
        onProfileSelect?.(activated);
      } catch (err) {
        toast.error('Failed to activate profile');
        console.error(err);
      } finally {
        setActivating(null);
      }
    },
    [onProfileSelect],
  );

  const activeProfile = profiles.find((p) => p.profile_key === activeKey);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
        {t('profile.loading', { default: 'Loading profiles...' })}
      </div>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="w-full justify-between">
          <div className="flex items-center gap-2">
            <IconShield className="h-4 w-4" />
            <span>{activeProfile?.display_name ?? t('profile.selectDefault', { default: 'Select Profile' })}</span>
          </div>
          <IconChevronDown className="h-4 w-4 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        {profiles.map((profile) => {
          const Icon = PROFILE_ICONS[profile.profile_key] ?? IconShield;
          const isActive = profile.profile_key === activeKey;
          const isActivatingThis = activating === profile.profile_key;

          return (
            <DropdownMenuItem
              key={profile.profile_key}
              onClick={() => handleActivate(profile.profile_key)}
              disabled={isActivatingThis}
              className="flex items-center gap-2"
            >
              <Icon className="h-4 w-4 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{profile.display_name}</div>
                {profile.description && (
                  <div className="text-xs text-muted-foreground truncate">{profile.description}</div>
                )}
              </div>
              {isActive && <IconCheck className="h-4 w-4 shrink-0 text-primary" />}
              {isActivatingThis && <IconLoader className="h-4 w-4 shrink-0 animate-spin" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
});

export default SecurityProfileSelector;
