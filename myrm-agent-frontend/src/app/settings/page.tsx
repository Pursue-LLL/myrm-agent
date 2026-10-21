import { redirect } from 'next/navigation';

/** Settings index: canonical routes use `/settings/[tab]`; default tab is account. */
export default function SettingsIndexPage() {
  redirect('/settings/account');
}
