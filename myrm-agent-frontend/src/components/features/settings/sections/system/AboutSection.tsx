'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconGlobe,
  IconBook,
  IconExternalLink,
  IconCode,
  IconZap,
  IconShield,
  IconFolder,
  IconBriefcase,
  IconClock,
} from '@/components/features/icons/PremiumIcons';
import { Users } from 'lucide-react';
import BrandLogo from '@/components/features/app-shell/BrandLogo';
import SettingsSection from '../SettingsSection';
import { cn } from '@/lib/utils/classnameUtils';
import { getDocsUrl, isTauriRuntime } from '@/lib/deploy-mode';

interface FeatureCardProps {
  icon: React.ElementType;
  title: string;
  description: string;
}

const FeatureCard = memo<FeatureCardProps>(({ icon: Icon, title, description }) => (
  <div className="flex gap-4 p-4 rounded-xl bg-background/50 border border-border/50 hover:border-primary/30 transition-colors">
    <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
      <Icon className="w-5 h-5 text-primary" />
    </div>
    <div className="flex-1 min-w-0">
      <h4 className="text-sm font-semibold text-foreground mb-1">{title}</h4>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
    </div>
  </div>
));

FeatureCard.displayName = 'FeatureCard';

interface LinkCardProps {
  icon: React.ElementType;
  title: string;
  description: string;
  href: string;
}

const LinkCard = memo<LinkCardProps>(({ icon: Icon, title, description, href }) => (
  <a
    href={href}
    target="_blank"
    rel="noopener noreferrer"
    className="flex items-center gap-4 p-4 rounded-xl bg-background/50 border border-border/50 hover:border-primary/50 hover:bg-accent/30 transition-all group"
  >
    <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
      <Icon className="w-5 h-5 text-primary" />
    </div>
    <div className="flex-1 min-w-0">
      <h4 className="text-sm font-semibold text-foreground mb-1 flex items-center gap-2">
        {title}
        <IconExternalLink className="w-3.5 h-3.5 text-muted-foreground group-hover:text-primary transition-colors" />
      </h4>
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  </a>
));

LinkCard.displayName = 'LinkCard';

interface TechBadgeProps {
  name: string;
  color: string;
}

const TechBadge = memo<TechBadgeProps>(({ name, color }) => (
  <div className={cn('px-3 py-1.5 rounded-lg text-xs font-medium border transition-all hover:scale-105', color)}>
    {name}
  </div>
));

TechBadge.displayName = 'TechBadge';

interface ChangelogItemProps {
  version: string;
  date: string;
  items: string[];
}

const ChangelogItem = memo<ChangelogItemProps>(({ version, date, items }) => (
  <div className="border-l-2 border-primary/30 pl-4 pb-6 last:pb-0">
    <div className="flex items-center gap-3 mb-2">
      <div className="flex items-center justify-center w-6 h-6 -ml-[1.4rem] rounded-full bg-primary/20 border-2 border-background">
        <div className="w-2 h-2 rounded-full bg-primary" />
      </div>
      <h4 className="text-sm font-bold text-foreground">v{version}</h4>
      <span className="text-xs text-muted-foreground">{date}</span>
    </div>
    <ul className="space-y-1 ml-5">
      {items.map((item, index) => (
        <li key={index} className="text-sm text-muted-foreground flex items-start gap-2">
          <span className="text-primary mt-1">•</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  </div>
));

ChangelogItem.displayName = 'ChangelogItem';

const FALLBACK_VERSION = '0.1.0';

const AboutSection = memo(() => {
  const t = useTranslations('settings.about');
  const [version, setVersion] = useState(FALLBACK_VERSION);

  useEffect(() => {
    if (!isTauriRuntime()) return;
    import('@tauri-apps/api/app')
      .then((mod) => mod.getVersion())
      .then((v) => setVersion(v))
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      {/* 应用信息区 */}
      <SettingsSection title={t('title')}>
        <div className="flex flex-col items-center text-center space-y-4 py-8">
          {/* Logo & 名称 */}
          <BrandLogo size={80} className="w-20 h-20" />
          <div className="space-y-2">
            <h1 className="text-3xl font-bold brand-gradient-text">MyrmAgent</h1>
            <p className="text-sm text-muted-foreground">{t('slogan')}</p>
            <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
              <IconBriefcase className="w-3.5 h-3.5" />
              <span>
                {t('version')} <span className="text-accent-warm font-medium">{version}</span>
              </span>
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* 项目简介 */}
      <SettingsSection title={t('introduction.title')}>
        <p className="text-sm text-muted-foreground leading-relaxed mb-6">{t('introduction.description')}</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FeatureCard
            icon={IconZap}
            title={t('features.powerful.title')}
            description={t('features.powerful.description')}
          />
          <FeatureCard
            icon={IconShield}
            title={t('features.secure.title')}
            description={t('features.secure.description')}
          />
          <FeatureCard
            icon={IconFolder}
            title={t('features.extensible.title')}
            description={t('features.extensible.description')}
          />
          <FeatureCard
            icon={IconCode}
            title={t('features.opensource.title')}
            description={t('features.opensource.description')}
          />
        </div>
      </SettingsSection>

      {/* 更新日志 */}
      <SettingsSection
        title={
          <div className="flex items-center gap-2">
            <IconClock className="w-5 h-5" />
            <span>{t('changelog.title')}</span>
          </div>
        }
        description={t('changelog.description')}
      >
        <div className="space-y-0">
          <ChangelogItem
            version="0.1.0"
            date="2026-01"
            items={[
              t('changelog.v0_1_0.item1'),
              t('changelog.v0_1_0.item2'),
              t('changelog.v0_1_0.item3'),
              t('changelog.v0_1_0.item4'),
            ]}
          />
        </div>
      </SettingsSection>

      {/* 技术栈 */}
      <SettingsSection title={t('techStack.title')} description={t('techStack.description')}>
        <div className="space-y-4">
          {/* 前端 */}
          <div>
            <h4 className="text-sm font-semibold text-foreground mb-3">{t('techStack.frontend')}</h4>
            <div className="flex flex-wrap gap-2">
              <TechBadge
                name="Next.js 16"
                color="bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100 border-slate-300 dark:border-slate-600"
              />
              <TechBadge
                name="React 19"
                color="bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700"
              />
              <TechBadge
                name="TypeScript"
                color="bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700"
              />
              <TechBadge
                name="Tailwind CSS"
                color="bg-cyan-50 dark:bg-cyan-950 text-cyan-700 dark:text-cyan-300 border-cyan-300 dark:border-cyan-700"
              />
              <TechBadge
                name="Zustand"
                color="bg-purple-50 dark:bg-purple-950 text-purple-700 dark:text-purple-300 border-purple-300 dark:border-purple-700"
              />
              <TechBadge
                name="Framer Motion"
                color="bg-pink-50 dark:bg-pink-950 text-pink-700 dark:text-pink-300 border-pink-300 dark:border-pink-700"
              />
            </div>
          </div>
          {/* 后端 */}
          <div>
            <h4 className="text-sm font-semibold text-foreground mb-3">{t('techStack.backend')}</h4>
            <div className="flex flex-wrap gap-2">
              <TechBadge
                name="Python 3.13"
                color="bg-yellow-50 dark:bg-yellow-950 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700"
              />
              <TechBadge
                name="FastAPI"
                color="bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700"
              />
              <TechBadge
                name="LiteLLM"
                color="bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 border-indigo-300 dark:border-indigo-700"
              />
              <TechBadge
                name="Qdrant"
                color="bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700"
              />
              <TechBadge
                name="SQLAlchemy"
                color="bg-orange-50 dark:bg-orange-950 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700"
              />
            </div>
          </div>
          {/* AI */}
          <div>
            <h4 className="text-sm font-semibold text-foreground mb-3">{t('techStack.ai')}</h4>
            <div className="flex flex-wrap gap-2">
              <TechBadge
                name="OpenAI"
                color="bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-700"
              />
              <TechBadge
                name="Anthropic"
                color="bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700"
              />
              <TechBadge
                name="MCP Protocol"
                color="bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-300 border-violet-300 dark:border-violet-700"
              />
              <TechBadge
                name="LangGraph"
                color="bg-teal-50 dark:bg-teal-950 text-teal-700 dark:text-teal-300 border-teal-300 dark:border-teal-700"
              />
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* 资源链接 */}
      <SettingsSection title={t('links.title')} description={t('links.description')}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <LinkCard
            icon={IconGlobe}
            title={t('links.website.title')}
            description={t('links.website.description')}
            href="https://myrmagent.com"
          />
          <LinkCard
            icon={IconGlobe}
            title={t('links.github.title')}
            description={t('links.github.description')}
            href="https://github.com/Pursue-LLL/myrm-agent"
          />
          <LinkCard
            icon={IconBook}
            title={t('links.documentation.title')}
            description={t('links.documentation.description')}
            href={getDocsUrl()}
          />
          <LinkCard
            icon={Users}
            title={t('links.community.title')}
            description={t('links.community.description')}
            href="https://discord.gg/myrmagent"
          />
        </div>
      </SettingsSection>

      {/* 许可证与版权 */}
      <SettingsSection title={t('license.title')}>
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-4 rounded-xl bg-background/50 border border-border/50">
            <IconShield className="w-[18px] h-[18px] text-primary mt-0.5" />
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-foreground mb-1">{t('license.type')}</h4>
              <p className="text-xs text-muted-foreground leading-relaxed">{t('license.description')}</p>
            </div>
          </div>
          <div className="text-center py-4">
            <p className="text-xs text-muted-foreground">
              {t('license.copyright', { year: new Date().getFullYear() })}
            </p>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
});

AboutSection.displayName = 'AboutSection';

export default AboutSection;
