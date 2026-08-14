"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { Menu, X } from "lucide-react";
import { BrandMark } from "@/components/brand/mark";
import { Sidebar, useSidebarCollapsed, type NavItem } from "@/components/layout/sidebar";
import { useSession } from "@/stores/session";
import { homeFor, cn } from "@/lib/utils";
import { founderNeedsOnboarding } from "@/lib/domain/onboarding";
import { useNotifications } from "@/lib/hooks/use-notifications";
import { useStartup } from "@/lib/hooks/use-startup";

export type { NavItem };

function titleFor(pathname: string, nav: NavItem[], home: string): string {
  const exact = nav.find((n) => n.href === pathname);
  if (exact) return exact.label;
  const nested = [...nav]
    .sort((a, b) => b.href.length - a.href.length)
    .find((n) => n.href !== home && pathname.startsWith(n.href));
  if (nested) return nested.label;
  if (pathname.includes("/alerts")) return "Alerts";
  if (pathname.includes("/profile")) return "Account";
  if (pathname.includes("/mfa-setup")) return "MFA setup";
  if (pathname.includes("/billing")) return "Billing";
  if (pathname.includes("/paywall")) return "Unlock";
  if (pathname.includes("/verify")) return "Verify";
  if (pathname.includes("/company")) return "Company";
  if (pathname.includes("/report")) return "Report";
  if (pathname.includes("/requests")) return "Inbox";
  if (pathname.includes("/interests")) return "Interests";
  return "Desk";
}

export function AppShell({
  role,
  nav,
  children,
}: {
  role: "founder" | "investor" | "admin";
  nav: NavItem[];
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const status = useSession((s) => s.status);
  const session = useSession((s) => s.session);
  const signOut = useSession((s) => s.signOut);
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  const drawerId = useId();
  const needsAdminMfa =
    status === "signedIn" &&
    session?.role === "admin" &&
    !session.mfaEnabled &&
    !pathname.startsWith("/admin/mfa-setup");
  const hideOpsNav = role === "admin" && session && !session.mfaEnabled;
  const { unread } = useNotifications(status === "signedIn" && !needsAdminMfa);
  const startup = useStartup(role === "founder" && status === "signedIn");
  const needsFounderIntake =
    role === "founder" &&
    status === "signedIn" &&
    !startup.loading &&
    !startup.error &&
    founderNeedsOnboarding(startup.profile);

  useEffect(() => {
    if (status === "signedOut") {
      router.replace(`/sign-in?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (status === "signedIn" && session && session.role !== role) {
      router.replace(homeFor(session.role));
      return;
    }
    if (needsAdminMfa) {
      router.replace("/admin/mfa-setup");
      return;
    }
    if (needsFounderIntake) {
      router.replace("/onboarding");
    }
  }, [status, session, role, router, pathname, needsAdminMfa, needsFounderIntake]);

  useEffect(() => {
    setMenuOpen(false);
    document.getElementById("main")?.focus();
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  if (status === "loading" || status === "signedOut") {
    return (
      <div className="flex min-h-dvh items-center justify-center text-mist">Opening Fundready…</div>
    );
  }

  if ((session && session.role !== role) || needsAdminMfa || (role === "founder" && (startup.loading || needsFounderIntake))) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-mist">Redirecting…</div>
    );
  }

  const home = homeFor(role);
  const pageTitle = titleFor(pathname, nav, home);
  const visibleNav = hideOpsNav ? [] : nav;

  async function handleSignOut() {
    await signOut();
    router.replace("/sign-in");
  }

  const sidebarProps = {
    role,
    nav: visibleNav,
    pathname,
    home,
    session: session!,
    unread,
    onSignOut: () => void handleSignOut(),
  };

  return (
    <div className="min-h-dvh bg-rail">
      <aside
        className={cn(
          "fixed top-3 bottom-3 left-3 z-20 hidden flex-col rounded-[22px] border border-black/5 bg-rail px-3 py-4 text-cream shadow-[0_8px_30px_rgba(16,28,44,0.06)] transition-[width] duration-200 ease-out lg:flex dark:border-white/10",
          collapsed ? "w-[76px]" : "w-[272px]",
        )}
      >
        <Sidebar
          {...sidebarProps}
          collapsed={collapsed}
          onCollapsedChange={setCollapsed}
          variant="rail"
        />
      </aside>

      {menuOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-navy/40"
            aria-label="Close menu"
            onClick={() => setMenuOpen(false)}
          />
          <div
            id={drawerId}
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
            className="absolute inset-y-3 left-3 flex w-[min(100%-24px,280px)] flex-col rounded-[22px] border border-black/5 bg-rail px-3 py-4 text-cream shadow-[0_16px_50px_rgba(16,28,44,0.18)] dark:border-white/10"
          >
            <button
              type="button"
              className="absolute top-3 right-3 z-10 flex h-11 w-11 cursor-pointer items-center justify-center rounded-[10px] text-cream hover:bg-rail-hover"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
            >
              <X size={20} />
            </button>
            <Sidebar
              {...sidebarProps}
              collapsed={false}
              onCollapsedChange={() => undefined}
              onNavigate={() => setMenuOpen(false)}
              variant="drawer"
            />
          </div>
        </div>
      ) : null}

      <div
        className={cn(
          "min-h-dvh transition-[padding] duration-200 ease-out",
          collapsed ? "lg:pl-[100px]" : "lg:pl-[296px]",
        )}
      >
        <header className="sticky top-0 z-10 flex h-14 items-center justify-between bg-rail/85 px-4 backdrop-blur-md lg:px-8">
          <div className="flex items-center gap-2 lg:hidden">
            <button
              type="button"
              className="flex h-11 w-11 cursor-pointer items-center justify-center text-cream"
              aria-label="Open menu"
              aria-expanded={menuOpen}
              aria-controls={drawerId}
              onClick={() => setMenuOpen(true)}
            >
              <Menu size={20} />
            </button>
            <BrandMark size={26} />
          </div>
          <div className="hidden text-sm font-semibold text-cream lg:block">{pageTitle}</div>
          <div className="lg:hidden" />
        </header>
        <main id="main" tabIndex={-1} className="px-5 py-6 outline-none lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
