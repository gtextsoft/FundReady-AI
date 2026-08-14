"use client";

import { Bookmark, Layers } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";

const NAV = [
  { href: "/investor", label: "Dealflow", icon: Layers },
  { href: "/investor/watchlist", label: "Watchlist", icon: Bookmark },
];

export default function InvestorLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="investor" nav={NAV}>
      {children}
    </AppShell>
  );
}
