"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Bell,
  ChevronsUpDown,
  CreditCard,
  Inbox,
  LogOut,
  Moon,
  PanelLeft,
  PanelLeftClose,
  Search,
  Settings,
  Sparkles,
  Sun,
  Zap,
} from "lucide-react";
import { BrandMark, Mark } from "@/components/brand/mark";
import { useColorScheme } from "@/components/ui/theme-toggle";
import { daysLeftInTrial, hasAccess } from "@/lib/domain/access";
import { founderAccount } from "@/lib/format";
import type { Session } from "@/lib/api";
import { cn } from "@/lib/utils";

export type NavItem = {
  href: string;
  label: string;
  group?: string;
  icon: LucideIcon;
};

type Role = "founder" | "investor" | "admin";

type RailItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: number;
};

const SIDEBAR_KEY = "fundready.sidebar";

function isActive(pathname: string, href: string, home: string) {
  return pathname === href || (href !== home && pathname.startsWith(href));
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0]![0]}${parts[1]![0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase() || "FR";
}

function firstName(name: string) {
  return name.trim().split(/\s+/)[0] || name;
}

function formatBadge(count: number) {
  if (count > 15) return "15+";
  return String(count);
}

function activityFor(role: Role, unread: number): RailItem[] {
  if (role === "founder") {
    return [
      { href: "/founder/requests", label: "Inbox", icon: Inbox },
      { href: "/founder/alerts", label: "Notifications", icon: Bell, badge: unread },
    ];
  }
  if (role === "investor") {
    return [
      { href: "/investor/interests", label: "Interests", icon: Inbox },
      { href: "/investor/alerts", label: "Notifications", icon: Bell, badge: unread },
    ];
  }
  return [{ href: "/admin/alerts", label: "Notifications", icon: Bell, badge: unread }];
}

function planLabel(role: Role, session: Session) {
  if (role === "founder") {
    if (session.subscriptionStatus === "active" || session.subscriptionStatus === "past_due") {
      return session.subscriptionStatus === "past_due" ? "Past due" : "Subscribed";
    }
    const days = daysLeftInTrial(founderAccount(session));
    return days > 0 ? "Trial" : "Locked";
  }
  if (role === "investor") return "Investor";
  return "Admin";
}

function promoFor(role: Role, session: Session) {
  if (role === "founder") {
    if (session.subscriptionStatus === "active" || session.subscriptionStatus === "past_due") {
      return null;
    }
    const account = founderAccount(session);
    const trial = hasAccess(account);
    const days = daysLeftInTrial(account);
    return {
      href: "/founder/paywall",
      kicker: trial ? `Current plan: Trial` : "Trial ended",
      body: trial
        ? `${days} day${days === 1 ? "" : "s"} left. Unlock to keep mentor, programmes, and dealflow listing.`
        : "A monthly subscription restores the desk after the trial.",
      cta: "Subscribe",
    };
  }
  return null;
}

function RailLink({
  href,
  icon: Icon,
  label,
  badge,
  active,
  collapsed,
  onClick,
}: RailItem & {
  active: boolean;
  collapsed: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      title={collapsed ? label : undefined}
      aria-label={collapsed ? (badge ? `${label}, ${formatBadge(badge)}` : label) : undefined}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex min-h-11 cursor-pointer items-center rounded-[10px] text-[13.5px] transition-colors duration-150",
        collapsed ? "justify-center px-0" : "gap-3 px-3",
        active
          ? "bg-rail-active font-semibold text-cream shadow-[0_1px_2px_rgba(16,28,44,0.07),0_6px_16px_rgba(16,28,44,0.06)] dark:shadow-none"
          : "font-medium text-text-muted hover:bg-rail-hover hover:text-cream",
      )}
    >
      <Icon size={18} strokeWidth={1.75} className="shrink-0" />
      <span
        className={cn(
          "min-w-0 flex-1 truncate transition-opacity duration-200",
          collapsed ? "sr-only" : "opacity-100",
        )}
      >
        {label}
      </span>
      {!collapsed && badge ? (
        <span className="min-w-5 rounded-full bg-surface-3 px-1.5 text-center text-[11px] font-semibold tabular-nums text-text-muted">
          {formatBadge(badge)}
        </span>
      ) : null}
      {collapsed && badge ? (
        <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-brand" aria-hidden />
      ) : null}
    </Link>
  );
}

function RailButton({
  icon: Icon,
  label,
  collapsed,
  onClick,
  pressed,
}: {
  icon: LucideIcon;
  label: string;
  collapsed: boolean;
  onClick: () => void;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={collapsed ? label : undefined}
      aria-label={label}
      aria-pressed={pressed}
      className={cn(
        "flex min-h-11 w-full cursor-pointer items-center rounded-[10px] text-[13.5px] font-medium text-text-muted transition-colors duration-150 hover:bg-rail-hover hover:text-cream",
        collapsed ? "justify-center px-0" : "gap-3 px-3",
      )}
    >
      <Icon size={18} strokeWidth={1.75} className="shrink-0" />
      <span className={cn("truncate", collapsed && "sr-only")}>{label}</span>
    </button>
  );
}

export function Sidebar({
  role,
  nav,
  pathname,
  home,
  session,
  unread,
  collapsed,
  onCollapsedChange,
  onNavigate,
  onSignOut,
  variant = "rail",
}: {
  role: Role;
  nav: NavItem[];
  pathname: string;
  home: string;
  session: Session;
  unread: number;
  collapsed: boolean;
  onCollapsedChange: (next: boolean) => void;
  onNavigate?: () => void;
  onSignOut: () => void;
  variant?: "rail" | "drawer";
}) {
  const compact = variant === "rail" && collapsed;
  const searchRef = useRef<HTMLInputElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);
  const [wantSearch, setWantSearch] = useState(false);
  const [modKey, setModKey] = useState("Ctrl");
  const { dark, toggle } = useColorScheme();
  const activity = useMemo(
    () => (nav.length ? activityFor(role, unread) : []),
    [nav.length, role, unread],
  );
  const menu = useMemo(() => {
    const activityHrefs = new Set(activity.map((item) => item.href));
    return nav.filter((item) => !activityHrefs.has(item.href));
  }, [activity, nav]);
  const promo = promoFor(role, session);
  const profileHref =
    role === "founder" ? "/founder/profile" : role === "investor" ? "/investor/profile" : "/admin/profile";
  const status = planLabel(role, session);

  const destinations = useMemo(() => {
    const extra: RailItem[] = [
      { href: profileHref, label: "Account", icon: Settings },
      ...(role === "founder" ? [{ href: "/founder/billing", label: "Billing", icon: CreditCard }] : []),
    ];
    return [...activity, ...menu, ...extra];
  }, [activity, menu, profileHref, role]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return destinations.filter((item) => item.label.toLowerCase().includes(q));
  }, [destinations, query]);

  useEffect(() => {
    setQuery("");
    setProfileOpen(false);
  }, [pathname]);

  useEffect(() => {
    setModKey(/Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl");
  }, []);

  function focusSearch() {
    if (collapsed) {
      onCollapsedChange(false);
      setWantSearch(true);
      return;
    }
    searchRef.current?.focus();
  }

  useEffect(() => {
    if (!wantSearch || collapsed) return;
    searchRef.current?.focus();
    setWantSearch(false);
  }, [wantSearch, collapsed]);

  useEffect(() => {
    if (variant !== "rail") return;
    function onKey(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "k") return;
      if (window.matchMedia("(max-width: 1023px)").matches) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }
      e.preventDefault();
      if (collapsed) {
        onCollapsedChange(false);
        setWantSearch(true);
        return;
      }
      searchRef.current?.focus();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [variant, collapsed, onCollapsedChange]);

  useEffect(() => {
    if (!profileOpen) return;
    function onDoc(e: MouseEvent) {
      if (!profileRef.current?.contains(e.target as Node)) setProfileOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setProfileOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [profileOpen]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className={cn(
          "flex shrink-0",
          compact ? "flex-col items-center gap-1 px-1 pt-1" : "items-center justify-between gap-2 px-1",
          variant === "drawer" && "pr-12",
        )}
      >
        <Link href={home} onClick={onNavigate} className="min-w-0" aria-label="Fundready home">
          {compact ? <Mark size={32} /> : <BrandMark size={32} />}
        </Link>
        {variant === "rail" ? (
          <button
            type="button"
            onClick={() => onCollapsedChange(!collapsed)}
            className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-[8px] text-text-faint hover:bg-rail-hover hover:text-cream"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={collapsed}
          >
            {collapsed ? <PanelLeft size={18} strokeWidth={1.75} /> : <PanelLeftClose size={18} strokeWidth={1.75} />}
          </button>
        ) : null}
      </div>

      <div className={cn("mt-5 shrink-0", compact ? "px-1" : "px-0.5")}>
        {compact ? (
          <button
            type="button"
            onClick={focusSearch}
            title="Quick search"
            aria-label="Quick search"
            className="flex h-11 w-full cursor-pointer items-center justify-center rounded-[10px] text-text-muted hover:bg-rail-hover hover:text-cream"
          >
            <Search size={18} strokeWidth={1.75} />
          </button>
        ) : (
          <label className="relative block">
            <span className="sr-only">Quick search</span>
            <Search
              size={16}
              strokeWidth={1.75}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-faint"
            />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Quick search"
              className="h-11 w-full rounded-[10px] border-0 bg-white pr-12 pl-9 text-sm text-cream outline-none ring-1 ring-black/5 placeholder:text-text-faint focus-visible:ring-2 focus-visible:ring-brand dark:bg-surface-2 dark:ring-white/10"
            />
            <kbd className="pointer-events-none absolute top-1/2 right-2.5 hidden -translate-y-1/2 rounded-md border border-line bg-surface px-1.5 py-0.5 text-[10px] font-semibold text-text-faint sm:inline">
              {modKey === "⌘" ? "⌘K" : "Ctrl+K"}
            </kbd>
          </label>
        )}
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-0.5">
        {results ? (
          <div className="grid gap-0.5">
            <p className="px-3 py-2 text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">Results</p>
            {results.length ? (
              results.map((item) => (
                <RailLink
                  key={item.href}
                  {...item}
                  active={isActive(pathname, item.href, home)}
                  collapsed={compact}
                  onClick={onNavigate}
                />
              ))
            ) : (
              <p className="px-3 py-2 text-sm text-text-faint">No matching pages.</p>
            )}
          </div>
        ) : (
          <>
            {activity.length ? (
              <div className="grid gap-0.5">
                {activity.map((item) => (
                  <RailLink
                    key={item.href}
                    {...item}
                    active={isActive(pathname, item.href, home)}
                    collapsed={compact}
                    onClick={onNavigate}
                  />
                ))}
              </div>
            ) : null}

            {activity.length && menu.length ? <div className="mx-2 my-3 h-px bg-line" /> : null}

            {menu.length ? (
              <nav className="grid gap-0.5" aria-label="Primary">
                {!compact && !menu.some((item) => item.group) ? (
                  <p className="mb-1 px-3 text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">
                    Menu
                  </p>
                ) : null}
                {menu.map((item, index) => {
                  const showGroup = Boolean(
                    !compact && item.group && item.group !== menu[index - 1]?.group,
                  );
                  return (
                    <div key={item.href}>
                      {showGroup ? (
                        <p className="mt-3 mb-1 px-3 text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">
                          {item.group}
                        </p>
                      ) : null}
                      <RailLink
                        href={item.href}
                        icon={item.icon}
                        label={item.label}
                        active={isActive(pathname, item.href, home)}
                        collapsed={compact}
                        onClick={onNavigate}
                      />
                    </div>
                  );
                })}
              </nav>
            ) : (
              <p className={cn("px-3 text-sm text-text-muted", compact && "sr-only")}>
                Enrol MFA to open the console.
              </p>
            )}

            {promo ? (
              compact ? (
                <Link
                  href={promo.href}
                  onClick={onNavigate}
                  title={promo.cta}
                  aria-label={promo.cta}
                  className="mx-auto mt-4 flex h-11 w-11 items-center justify-center rounded-full border border-brand/30 text-brand hover:bg-rail-promo"
                >
                  <Sparkles size={18} strokeWidth={1.75} />
                </Link>
              ) : (
                <div className="mt-4 rounded-2xl bg-rail-promo px-4 py-4">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-brand shadow-sm dark:bg-surface">
                    <Sparkles size={16} strokeWidth={1.75} />
                  </div>
                  <p className="mt-3 text-[13px] font-semibold text-cream">{promo.kicker}</p>
                  <p className="mt-1 text-[12px] leading-5 text-text-muted">{promo.body}</p>
                  <Link
                    href={promo.href}
                    onClick={onNavigate}
                    className="mt-3 inline-flex min-h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-[10px] bg-white text-[13px] font-semibold text-cream shadow-sm ring-1 ring-black/5 hover:ring-brand/30 dark:bg-surface dark:ring-white/10"
                  >
                    <Zap size={14} strokeWidth={2} className="text-brand" />
                    {promo.cta}
                  </Link>
                </div>
              )
            ) : null}
          </>
        )}
      </div>

      <div className="mt-auto shrink-0 pt-2">
        <div className={cn("mx-2 mb-2 h-px bg-line", compact && "mx-1")} />
        <div className="grid gap-0.5 px-0.5">
          <RailLink
            href={profileHref}
            icon={Settings}
            label="Preferences"
            active={pathname === profileHref}
            collapsed={compact}
            onClick={onNavigate}
          />
          <RailButton
            icon={dark ? Sun : Moon}
            label={dark ? "Light mode" : "Dark mode"}
            collapsed={compact}
            onClick={toggle}
            pressed={dark}
          />
        </div>

        <div className="mx-2 my-2 h-px bg-line" />

        <div ref={profileRef} className="relative px-0.5">
          {profileOpen ? (
            <div
              role="menu"
              className={cn(
                "absolute z-30 min-w-[200px] rounded-xl border border-line bg-surface p-1 shadow-[0_12px_40px_rgba(16,28,44,0.12)]",
                compact ? "bottom-0 left-[calc(100%+10px)]" : "right-0 bottom-[calc(100%+8px)] left-0",
              )}
            >
              <Link
                href={profileHref}
                role="menuitem"
                onClick={() => {
                  setProfileOpen(false);
                  onNavigate?.();
                }}
                className="flex min-h-10 items-center gap-2 rounded-[8px] px-3 text-sm text-cream hover:bg-rail-hover"
              >
                <Settings size={16} strokeWidth={1.75} />
                Account
              </Link>
              {role === "founder" ? (
                <Link
                  href="/founder/billing"
                  role="menuitem"
                  onClick={() => {
                    setProfileOpen(false);
                    onNavigate?.();
                  }}
                  className="flex min-h-10 items-center gap-2 rounded-[8px] px-3 text-sm text-cream hover:bg-rail-hover"
                >
                  <CreditCard size={16} strokeWidth={1.75} />
                  Billing
                </Link>
              ) : null}
              <button
                type="button"
                role="menuitem"
                onClick={onSignOut}
                className="flex min-h-10 w-full cursor-pointer items-center gap-2 rounded-[8px] px-3 text-sm text-fail hover:bg-rail-hover"
              >
                <LogOut size={16} strokeWidth={1.75} />
                Sign out
              </button>
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setProfileOpen((open) => !open)}
            aria-haspopup="menu"
            aria-expanded={profileOpen}
            title={compact ? session.displayName : undefined}
            className={cn(
              "flex min-h-12 w-full cursor-pointer items-center rounded-[12px] text-left hover:bg-rail-hover",
              compact ? "justify-center" : "gap-3 px-2 py-1.5",
            )}
          >
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand text-[11px] font-bold tracking-wide text-white">
              {initials(session.displayName)}
            </span>
            <span className={cn("min-w-0 flex-1", compact && "sr-only")}>
              <span className="block truncate text-[13.5px] font-semibold text-cream">
                {firstName(session.displayName)}
              </span>
              <span className="block truncate text-[12px] text-text-faint">{status}</span>
            </span>
            <ChevronsUpDown
              size={16}
              strokeWidth={1.75}
              className={cn("shrink-0 text-text-faint", compact && "sr-only")}
            />
          </button>
        </div>
      </div>
    </div>
  );
}

export function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(SIDEBAR_KEY) === "collapsed") setCollapsed(true);
  }, []);

  function set(next: boolean) {
    setCollapsed(next);
    localStorage.setItem(SIDEBAR_KEY, next ? "collapsed" : "expanded");
  }

  return [collapsed, set] as const;
}
