'use client';

import WaitingTtftIndicator from './WaitingTtftIndicator';

/**
 * Loading bubble shown until the turn produces its first visible message.
 *
 * The bars keep the familiar skeleton silhouette, but a bare skeleton reads as "frozen" when the
 * model takes several seconds to emit its first token. The live counter above it makes progress
 * explicit even before routing/message frames arrive.
 */
const MessageBoxLoading = () => (
  <div className="w-full rounded-lg bg-background py-3 lg:w-9/12">
    <WaitingTtftIndicator />
    <div className="mt-2 flex animate-pulse flex-col space-y-2" aria-hidden="true">
      <div className="h-2 w-full rounded-full bg-secondary" />
      <div className="h-2 w-9/12 rounded-full bg-secondary" />
      <div className="h-2 w-10/12 rounded-full bg-secondary" />
    </div>
  </div>
);

export default MessageBoxLoading;
