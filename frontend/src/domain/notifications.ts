import { C } from '@/theme/tokens';
import type { Role } from '@/api/contract';

/**
 * The in-app notification centre, shared by both sides.
 *
 * Each notification is addressed to an audience (`founder` or `investor`) so
 * the same event log can serve both — an investor requesting a call writes one
 * notification to the founder, and the founder's answer writes one back.
 */

export type NotificationKind =
  | 'call_requested'
  | 'call_accepted'
  | 'call_declined'
  | 'intro_requested'
  | 'intro_accepted'
  | 'verification_approved'
  | 'verification_rejected'
  | 'payment_receipt'
  | 'trial_ending'
  | 'score_changed'
  | 'new_matches';

export type AppNotification = {
  id: string;
  audience: Role;
  kind: NotificationKind;
  title: string;
  body: string;
  /** ISO timestamp. */
  createdAt: string;
  read: boolean;
  /** Deep-link target, when the notification is about a specific company. */
  companyId?: number;
  /** Set on `call_requested` so the founder can accept or decline in place. */
  callRequestId?: string;
};

export type CallRequestStatus = 'pending' | 'accepted' | 'declined';

/** A virtual call an investor has asked a founder for. */
export type CallRequest = {
  id: string;
  companyId: number;
  companyName: string;
  investorName: string;
  investorFirm: string;
  /** ISO datetime of the proposed slot. */
  proposedAt: string;
  durationMinutes: number;
  note: string;
  status: CallRequestStatus;
};

const DOT: Record<NotificationKind, string> = {
  call_requested: C.info,
  call_accepted: C.signal,
  call_declined: C.alert,
  intro_requested: C.info,
  intro_accepted: C.signal,
  verification_approved: C.signal,
  verification_rejected: C.alert,
  payment_receipt: C.signal,
  trial_ending: C.flag,
  score_changed: C.signal,
  new_matches: C.flag,
};

export function notificationColor(kind: NotificationKind): string {
  return DOT[kind] ?? C.info;
}

/** "2h ago", "Yesterday", "12 Jul" — relative until it stops being useful. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  const mins = Math.round((now - then) / 60_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

/** "Thu 31 Jul · 14:00" — how a proposed call slot reads everywhere. */
export function formatSlot(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${day} · ${time}`;
}
