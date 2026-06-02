import ChatWindowNew from '@/components/ui/chat-window/ChatWindow';
import { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';

export async function generateMetadata(props: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const params = await props.params;
  const { locale } = params;

  const t = await getTranslations({ locale, namespace: 'metadata' });

  return {
    title: t('chatPageTitle'),
    description: t('chatPageDescription'),
  };
}

const Home = () => {
  return <ChatWindowNew />;
};

export default Home;
