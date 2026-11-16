'use client';

/**
 * [INPUT]
 * - @/components/dev/E2EChatBridge (POS: App shell dev bridge，聊天桥的挂载组件)
 * - @/components/dev/E2EWikiBridge (POS: Wiki 设置页与迁移向导的 Chrome E2E 桥)
 * - @/components/dev/localDevHost::isLocalDevHost (POS: 开发桥的挂载守卫)
 *
 * [OUTPUT]
 * - E2eBridgeLoader: mounts the chat and wiki bridges in a non-production build served from a local dev host only
 *
 * [POS]
 * Root-level localhost E2E bridge — mounts outside LocalizedProviders Suspense so
 * CDP Chrome E2E can reach attachToChat when Turbopack/RSC is slow under parallel load.
 * The root layout renders it only in non-production builds.
 */
import E2EChatBridge from '@/components/dev/E2EChatBridge';
import E2EWikiBridge from '@/components/dev/E2EWikiBridge';
import { isLocalDevHost } from '@/components/dev/localDevHost';

export default function E2eBridgeLoader() {
  // The production literal lets a build drop the bridge imports; isLocalDevHost keeps the bridges to loopback hosts.
  if (process.env.NODE_ENV === 'production' || !isLocalDevHost()) {
    return null;
  }
  return (
    <>
      <E2EChatBridge />
      <E2EWikiBridge />
    </>
  );
}
