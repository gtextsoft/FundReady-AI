"use client";

import { BadgeCheck, BarChart3, Building2, ListTodo, Package, Users } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";

const NAV = [
  { href: "/admin", label: "Queue", group: "Operations", icon: ListTodo },
  { href: "/admin/verifications", label: "Verifications", group: "Operations", icon: BadgeCheck },
  { href: "/admin/startups", label: "Startups", group: "Operations", icon: Building2 },
  { href: "/admin/products", label: "Products", group: "Catalog", icon: Package },
  { href: "/admin/benchmarks", label: "Benchmarks", group: "Catalog", icon: BarChart3 },
  { href: "/admin/users", label: "Users", group: "System", icon: Users },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell role="admin" nav={NAV}>
      {children}
    </AppShell>
  );
}
