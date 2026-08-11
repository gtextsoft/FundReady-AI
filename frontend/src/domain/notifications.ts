import { C } from '@/theme/tokens';
import type { Role } from '@/api/contract';

/**
 * The in-app notification centre, shared by both sides.
 *
 * Each notification is addressed to an audience (`founder` or `investor`) so
 * the same event log can serve both — an investor requesting a call writes one
 * notification to the founder, and the founder's answer writes one back.
 */

/** Stable server event type, e.g. `call_requested`, `task_assigned`. */
export type NotificationKind = string;

export type AppNotification = {
  id: string;
  audience: Role;
  kind: NotificationKind;
  title: string;
  body: string;
  /** ISO timestamp. */
  createdAt: string;
  read: boolean;
  /** Deep-link target when the payload carries a startup id. */
  startupId?: string;
  /** Set on call-related alerts so the founder can answer in place. */
  callRequestId?: string;
};

export type CallRequestStatus = 'pending' | 'accepted' | 'declined';

/** A virtual call an investor has asked a founder for (`GET /v1/calls`). */
export type CallRequest = {
  id: string;
  interestId: string;
  /** ISO datetime of the proposed slot. */
  proposedAt: string;
  message: string | null;
  status: CallRequestStatus;
  createdAt: string;
  respondedAt: string | null;
};

const DOT: Record<string, string> = {
  call_requested: C.blue,
  call_accepted: C.grn,
  call_declined: C.red,
  intro_requested: C.blue,
  intro_accepted: C.grn,
  interest_received: C.blue,
  interest_approved: C.grn,
  interest_declined: C.red,
  verification_approved: C.grn,
  verification_rejected: C.red,
  kyc_verified: C.grn,
  kyc_failed: C.red,
  payment_receipt: C.grn,
  trial_ending: C.amb,
  score_changed: C.grn,
  new_matches: C.amb,
  task_assigned: C.amb,
  meeting_booked: C.blue,
};

export function notificationColor(kind: NotificationKind): string {
  return DOT[kind] ?? C.blue;
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
