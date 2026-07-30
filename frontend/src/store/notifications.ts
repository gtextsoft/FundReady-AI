import { create } from 'zustand';
import { api, type Role } from '@/api';
import type { AppNotification, CallRequest } from '@/domain/notifications';

type NotificationState = {
  items: AppNotification[];
  callRequests: CallRequest[];
  loading: boolean;
  /** Why the inbox is empty, when it is empty because nothing served it. */
  error: unknown;

  unreadCount(): number;
  /** Call requests still awaiting the founder's answer. */
  pendingCalls(): CallRequest[];

  load(audience: Role): Promise<void>;
  markAllRead(): Promise<void>;
  respondToCall(id: string, accept: boolean): Promise<void>;
};

export const useNotifications = create<NotificationState>((set, get) => ({
  items: [],
  callRequests: [],
  loading: false,
  error: null,

  unreadCount() {
    return get().items.filter((n) => !n.read).length;
  },

  pendingCalls() {
    return get().callRequests.filter((r) => r.status === 'pending');
  },

  async load(audience) {
    set({ loading: true, error: null });
    try {
      // The founder's inbox needs the call requests themselves, not just the
      // notifications about them, so accept/decline can act in place.
      const [items, callRequests] = await Promise.all([
        api.listNotifications(audience),
        audience === 'founder' ? api.listCallRequests() : Promise.resolve([]),
      ]);
      set({ items, callRequests, loading: false });
    } catch (error) {
      set({ items: [], callRequests: [], loading: false, error });
    }
  },

  async markAllRead() {
    const unread = get().items.filter((n) => !n.read).map((n) => n.id);
    if (!unread.length) return;
    set((s) => ({ items: s.items.map((n) => ({ ...n, read: true })) }));
    // Marking read is not worth surfacing a failure over; the next load wins.
    await api.markNotificationsRead(unread).catch(() => undefined);
  },

  async respondToCall(id, accept) {
    const updated = await api.respondToCall(id, accept);
    set((s) => ({
      callRequests: s.callRequests.map((r) => (r.id === id ? updated : r)),
    }));
  },
}));
