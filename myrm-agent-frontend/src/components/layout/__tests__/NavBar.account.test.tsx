/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../NavBar (POS: 左侧导航栏，头像按钮打开账号菜单)
 *
 * [OUTPUT]
 * Vitest: 访客与登录用户的账号菜单、订阅入口随部署模式出现、头像加载失败的降级与换图后的重试、
 * 导航栏更新时头像元素保持不变、移动端点击菜单项先收起侧栏、仅开发构建提供的测试登录。
 *
 * [POS]
 * 订阅、路由与部署模式由 navBarKit 提供替身；登录 store、文案与登录重定向路径是真实的。
 */
import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kit, renderNavBar, resetNavBarKit, setAccount, signedIn } from './navBarKit';
import { buildAuthLoginPath } from '@/lib/auth-redirect';
import { expectDefined } from '@/test-utils/expectDefined';

const openAccountMenu = (name: string) => fireEvent.click(screen.getByRole('button', { name }));
const menu = () => within(screen.getByRole('dialog'));
const menuLink = (href: string) => {
  const link = menu()
    .getAllByRole('link')
    .find((candidate) => candidate.getAttribute('href') === href);
  expectDefined(link, `menu link ${href}`);
  return link;
};

describe('NavBar account menu', () => {
  beforeEach(resetNavBarKit);
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('as a guest', () => {
    it('offers to sign in and sends the guest back to the page they came from afterwards', () => {
      renderNavBar({ currentPathname: '/chat/c1' });

      openAccountMenu('Guest');
      fireEvent.click(menu().getByRole('button', { name: 'Log In' }));

      expect(kit.router.push).toHaveBeenCalledExactlyOnceWith(buildAuthLoginPath('/chat/c1'));
    });

    it('signs in without a page to return to when there is none', () => {
      renderNavBar({ currentPathname: '' });

      openAccountMenu('Guest');
      fireEvent.click(menu().getByRole('button', { name: 'Log In' }));

      expect(kit.router.push).toHaveBeenCalledExactlyOnceWith('/auth/login');
    });

    it('cannot start a second sign-in while one is in progress', () => {
      setAccount({ isLoading: true });
      renderNavBar();

      openAccountMenu('Guest');

      expect(menu().getByRole('button', { name: 'Log In' })).toBeDisabled();
    });

    it.each([
      [true, 1],
      [false, 0],
    ])('with isMobile=%s closes the sidebar %i time(s) before leaving for the sign-in page', (isMobile, closed) => {
      const { onCloseMobileSidebar } = renderNavBar({ isMobile });

      openAccountMenu('Guest');
      fireEvent.click(menu().getByRole('button', { name: 'Log In' }));

      expect(onCloseMobileSidebar).toHaveBeenCalledTimes(closed);
    });

    it('links to settings, and shows no plans in a local deployment', () => {
      renderNavBar();

      openAccountMenu('Guest');

      expect(menuLink('/settings')).toHaveTextContent('Settings');
      expect(menu().queryByRole('link', { name: /Upgrade/ })).toBeNull();
    });

    it('promotes the upgrade on a hosted deployment, and closes the mobile sidebar when it is followed', () => {
      kit.deploy.local = false;
      const { onCloseMobileSidebar } = renderNavBar({ isMobile: true });

      openAccountMenu('Guest');
      fireEvent.click(menuLink('/pricing'));

      expect(menuLink('/pricing')).toHaveTextContent('Upgrade to Pro');
      expect(onCloseMobileSidebar).toHaveBeenCalledOnce();
    });

    it('never offers the test login outside a development build', () => {
      renderNavBar();

      openAccountMenu('Guest');

      expect(menu().queryByRole('button', { name: 'Test Login' })).toBeNull();
    });

    describe('in a development build', () => {
      beforeEach(() => {
        vi.stubEnv('NODE_ENV', 'development');
      });
      afterEach(() => {
        vi.unstubAllEnvs();
      });

      it('signs in as a test user in one click, closing the mobile sidebar first', () => {
        const { onCloseMobileSidebar } = renderNavBar({ isMobile: true });

        openAccountMenu('Guest');
        fireEvent.click(menu().getByRole('button', { name: 'Test Login' }));

        expect(onCloseMobileSidebar).toHaveBeenCalledOnce();
        expect(kit.auth.loginMock).toHaveBeenCalledOnce();
        expect(kit.router.push).not.toHaveBeenCalled();
      });

      it('cannot start a test login while a sign-in is in progress', () => {
        setAccount({ isLoading: true });
        renderNavBar();

        openAccountMenu('Guest');

        expect(menu().getByRole('button', { name: 'Test Login' })).toBeDisabled();
      });
    });
  });

  describe('when signed in', () => {
    beforeEach(() => {
      setAccount({ user: { ...signedIn } });
    });

    it('shows who is signed in, with the email underneath when it differs from the name', () => {
      renderNavBar();

      openAccountMenu('Ada Lovelace');

      expect(menu().getByText('Ada Lovelace')).toBeInTheDocument();
      expect(menu().getByText('ada@example.com')).toBeInTheDocument();
    });

    it('falls back to the email when there is no display name, without repeating it', () => {
      setAccount({ user: { id: 'u2', email: 'grace@example.com' } });
      renderNavBar();

      openAccountMenu('grace@example.com');

      expect(menu().getAllByText('grace@example.com')).toHaveLength(1);
    });

    it('signs out, closing the mobile sidebar first', () => {
      const { onCloseMobileSidebar } = renderNavBar({ isMobile: true });

      openAccountMenu('Ada Lovelace');
      fireEvent.click(menu().getByRole('button', { name: 'Log Out' }));

      expect(onCloseMobileSidebar).toHaveBeenCalledOnce();
      expect(kit.auth.logout).toHaveBeenCalledOnce();
    });

    it('has no plan entries in a local deployment', () => {
      renderNavBar();

      openAccountMenu('Ada Lovelace');

      expect(menu().queryByRole('link', { name: /Upgrade|Pro|Subscription/ })).toBeNull();
    });

    it.each([
      [false, 'Upgrade to Pro'],
      [true, 'Pro'],
    ])('shows the plan entry for isPro=%s as "%s" on a hosted deployment', (isPro, label) => {
      kit.deploy.local = false;
      kit.subscription.isPro = isPro;
      renderNavBar();

      openAccountMenu('Ada Lovelace');

      expect(menuLink('/pricing')).toHaveTextContent(label);
      expect(menuLink('/subscription')).toHaveTextContent('Subscription');
    });

    it('closes the mobile sidebar when any menu link is followed', () => {
      kit.deploy.local = false;
      const { onCloseMobileSidebar } = renderNavBar({ isMobile: true });

      openAccountMenu('Ada Lovelace');
      for (const href of ['/pricing', '/subscription', '/settings']) {
        fireEvent.click(menuLink(href));
      }

      expect(onCloseMobileSidebar).toHaveBeenCalledTimes(3);
    });
  });

  describe('the avatar', () => {
    const PICTURE = 'https://cdn.example.com/ada.png';
    const NEW_PICTURE = 'https://cdn.example.com/ada-new.png';

    beforeEach(() => {
      setAccount({ user: { ...signedIn, avatar_url: PICTURE } });
    });

    it('shows the picture of the signed-in user', () => {
      renderNavBar();

      expect(screen.getByRole('img', { name: 'Ada Lovelace' })).toHaveAttribute('src', PICTURE);
    });

    it('falls back to the person icon when the picture cannot be loaded', () => {
      renderNavBar();

      fireEvent.error(screen.getByRole('img', { name: 'Ada Lovelace' }));

      expect(screen.queryByRole('img')).toBeNull();
    });

    it('tries again with a picture the user changes to after the old one failed', () => {
      renderNavBar();
      fireEvent.error(screen.getByRole('img', { name: 'Ada Lovelace' }));
      expect(screen.queryByRole('img')).toBeNull();

      setAccount({ user: { ...signedIn, avatar_url: NEW_PICTURE } });

      expect(screen.getByRole('img', { name: 'Ada Lovelace' })).toHaveAttribute('src', NEW_PICTURE);
    });

    it('keeps the same picture element while the rail updates around it', () => {
      const { rerenderWith } = renderNavBar();
      const picture = screen.getByRole('img', { name: 'Ada Lovelace' });

      rerenderWith({ activeTab: 'work' });

      expect(screen.getByRole('img', { name: 'Ada Lovelace' })).toBe(picture);
    });
  });
});
