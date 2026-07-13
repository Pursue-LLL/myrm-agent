import ChatWindowNew from '@/components/features/chat-window/ChatWindow';
import { Metadata } from 'next';
import { getBuildTimeMetadataMessages } from '@/lib/metadata/static-metadata';

const metadataMessages = getBuildTimeMetadataMessages();

export const metadata: Metadata = {
  title: metadataMessages.chatPageTitle,
  description: metadataMessages.chatPageDescription,
};

const Home = () => {
  return <ChatWindowNew />;
};

export default Home;
