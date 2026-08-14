"use client";

import { ClipboardCheck, GraduationCap, LayoutDashboard, MessageCircle, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";

const NAV = [
  { href: "/founder", label: "Home", icon: LayoutDashboard },
  { href: "/founder/tasks", label: "Readiness", icon: ClipboardCheck },
  { href: "/founder/mentor", label: "Mentor", icon: MessageCircle },
  { href: "/founder/programmes", label: "Programmes", icon: GraduationCap },
  { href: "/founder/verify", label: "Verify", icon: ShieldCheck },
];

export default function FounderLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="founder" nav={NAV}>
      {children}
    </AppShell>
  );
}
