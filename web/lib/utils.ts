import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function displayName(first: string | null, last: string | null, email: string) {
  const given = `${first ?? ""} ${last ?? ""}`.trim();
  if (given) return given;
  const handle = email.split("@")[0] || "there";
  return handle.replace(/[._-]+/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

export function formatMoney(minor: number | null, currency: string | null) {
  if (minor == null || !currency) return "—";
  const zeroDecimal = new Set(["JPY", "KRW", "VND", "CLP", "ISK", "XAF", "XOF", "UGX", "RWF"]);
  const amount = zeroDecimal.has(currency) ? minor : minor / 100;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: zeroDecimal.has(currency) ? 0 : 0,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toLocaleString()}`;
  }
}

export function relativeTime(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  const mins = Math.round((now - then) / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function formatSlot(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const time = d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${day} · ${time}`;
}

export function homeFor(role: "founder" | "investor" | "admin") {
  if (role === "founder") return "/founder";
  if (role === "investor") return "/investor";
  return "/admin";
}

export function landingFor(
  session: { role: "founder" | "investor" | "admin"; mfaEnabled: boolean },
  next?: string | null,
) {
  if (session.role === "admin" && !session.mfaEnabled) return "/admin/mfa-setup";
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return homeFor(session.role);
}
