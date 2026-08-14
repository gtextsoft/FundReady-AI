"use client";

import { useEffect, useState } from "react";
import { api, type NotificationItem } from "@/lib/api";

export function useNotifications(enabled: boolean) {
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let stop = false;
    async function tick() {
      try {
        const page = await api.listNotifications();
        if (stop) return;
        setItems(page.items);
        setUnread(page.items.filter((n) => !n.read_at).length);
      } catch {
        /* polling is best-effort */
      }
    }
    void tick();
    const id = setInterval(() => void tick(), 30_000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [enabled]);

  return { unread, items };
}
