import { Metadata } from 'next';

import CanvasListPage from '@/components/features/canvas/CanvasListPage';

export const metadata: Metadata = {
  title: 'Canvas Workspaces',
};

export default function CanvasPage() {
  return <CanvasListPage />;
}
