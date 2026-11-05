'use client';

/**
 * [INPUT]
 * - ./useNavMoreSections::useNavMoreSections (POS: grouped destinations and tools)
 * - Radix DropdownMenu/Tooltip primitives, next-intl nav namespace
 * - lib/utils/componentPreloader::preloadMonacoEditor (POS: warm the editor chunk before a page that needs it)
 *
 * [OUTPUT]
 * - NavMoreMenu: the rail's single "More" entry
 *
 * [POS]
 * Keeps the rail to its primary destinations: monitoring pages, extension surfaces and the secondary tool panels
 * open from one labelled menu. The entry lights up while the current route is one of its destinations, and the menu
 * is capped to the available height and scrolls, so it never runs off a short window. Focus returns to the entry
 * only when the keyboard closes the menu. The tool panels stay mounted globally (i18n/LocalizedProviders); this
 * component only dispatches their open action.
 */

import { Fragment, useRef, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { DotsNine } from '@phosphor-icons/react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { preloadMonacoEditor } from '@/lib/utils/componentPreloader';
import { cn } from '@/lib/utils/classnameUtils';
import { useNavMoreSections, type NavMoreActionItem, type NavMoreLinkItem } from './useNavMoreSections';

interface NavMoreMenuProps {
  currentPathname: string;
  extensionConnected: boolean;
  /** Runs when a destination is chosen, e.g. to close the mobile drawer. */
  onNavigate: () => void;
}

// Touch screens get 44px rows; the shortcut chips are dropped there because a touch screen has no keys to press.
const ROW_CLASS = 'gap-2 rounded-lg px-2 py-2 text-foreground pointer-coarse:py-3 focus:bg-muted focus:text-foreground';

function isRouteActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function LinkRow({ item, active, onNavigate }: { item: NavMoreLinkItem; active: boolean; onNavigate: () => void }) {
  const Icon = item.icon;

  return (
    <DropdownMenuItem asChild className={cn(ROW_CLASS, active && 'bg-primary/10')}>
      <Link
        href={item.href}
        aria-current={active ? 'page' : undefined}
        onClick={onNavigate}
        onMouseEnter={item.preloadsEditor ? preloadMonacoEditor : undefined}
      >
        <Icon
          size={16}
          className={cn('shrink-0', active ? 'text-primary' : 'text-muted-foreground')}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1 truncate">{item.label}</span>
        {item.connection && (
          <span
            aria-hidden="true"
            className={cn(
              'h-2 w-2 shrink-0 rounded-full',
              item.connection === 'connected'
                ? 'bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.14)]'
                : 'bg-muted-foreground/40 shadow-[0_0_0_3px_rgba(156,163,175,0.12)]',
            )}
          />
        )}
      </Link>
    </DropdownMenuItem>
  );
}

function ActionRow({ item }: { item: NavMoreActionItem }) {
  const Icon = item.icon;
  // Only the docked workbench is a toggle. An explicit `role: undefined` would erase the item's default role, so the
  // toggle semantics are spread in only when they apply.
  const toggleProps = item.pressed === undefined ? {} : { role: 'menuitemcheckbox', 'aria-checked': item.pressed };

  return (
    <DropdownMenuItem
      onSelect={item.action}
      className={cn(ROW_CLASS, item.pressed && 'bg-primary/10')}
      {...toggleProps}
    >
      <Icon
        size={16}
        className={cn('shrink-0', item.pressed ? 'text-primary' : 'text-muted-foreground')}
        aria-hidden="true"
      />
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
      <kbd className="shrink-0 rounded border border-border/40 bg-background/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground pointer-coarse:hidden">
        {item.shortcut}
      </kbd>
    </DropdownMenuItem>
  );
}

export function NavMoreMenu({ currentPathname, extensionConnected, onNavigate }: NavMoreMenuProps) {
  const t = useTranslations('nav');
  const sections = useNavMoreSections(extensionConnected);
  const [open, setOpen] = useState(false);
  // Radix hands focus back to the trigger when the menu closes. After a pointer pick or a click outside that only
  // paints a focus ring and reopens the tooltip beside a page the user already moved on to, so focus is restored for
  // keyboard closes only.
  const lastInputWasPointer = useRef(false);
  const markPointerInput = () => {
    lastInputWasPointer.current = true;
  };
  const markKeyboardInput = () => {
    lastInputWasPointer.current = false;
  };

  const handleOpenChange = (next: boolean) => {
    // Each session starts from the keyboard default, so a pointer pick in an earlier session cannot leak into this one.
    if (next) {
      markKeyboardInput();
    }
    setOpen(next);
  };

  const routeActive = (item: NavMoreLinkItem) => isRouteActive(currentPathname, item.href);
  const insideDestination = sections.some((section) =>
    section.items.some((item) => item.kind === 'link' && routeActive(item)),
  );

  return (
    <DropdownMenu open={open} onOpenChange={handleOpenChange}>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={t('more')}
              aria-current={insideDestination ? 'true' : undefined}
              data-testid="nav-more-trigger"
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200',
                open || insideDestination
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-primary/5 hover:text-accent-warm hover:shadow-brand',
              )}
            >
              <DotsNine size={20} weight="bold" aria-hidden="true" />
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="right">{t('more')}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent
        side="right"
        align="start"
        sideOffset={10}
        collisionPadding={8}
        data-testid="nav-more-menu"
        className="w-64 rounded-xl p-1.5"
        onPointerDownCapture={markPointerInput}
        onPointerDownOutside={markPointerInput}
        onKeyDownCapture={markKeyboardInput}
        onCloseAutoFocus={(event) => {
          if (lastInputWasPointer.current) {
            event.preventDefault();
          }
        }}
      >
        {sections.map((section, index) => (
          <Fragment key={section.id}>
            {index > 0 && <DropdownMenuSeparator className="-mx-1.5 my-1.5" />}
            <DropdownMenuGroup aria-labelledby={`nav-more-${section.id}`}>
              <DropdownMenuLabel
                id={`nav-more-${section.id}`}
                className="px-2 py-1 text-xs font-medium text-muted-foreground"
              >
                {section.title}
              </DropdownMenuLabel>
              {section.items.map((item) =>
                item.kind === 'link' ? (
                  <LinkRow key={item.id} item={item} active={routeActive(item)} onNavigate={onNavigate} />
                ) : (
                  <ActionRow key={item.id} item={item} />
                ),
              )}
            </DropdownMenuGroup>
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
