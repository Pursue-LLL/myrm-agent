import { Metadata } from 'next';
import { getBuildTimeMetadataMessages } from '@/lib/metadata/static-metadata';
import ResearchLayout from '@/components/features/research/ResearchLayout';

const metadataMessages = getBuildTimeMetadataMessages();

export const metadata: Metadata = {
  title: `Research | ${metadataMessages.chatPageTitle}`,
};

export default function ResearchPage() {
  return <ResearchLayout />;
}
