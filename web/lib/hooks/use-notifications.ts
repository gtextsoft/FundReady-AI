"use client";

import { useEffect, useState } from "react";
import { api, type NotificationItem } from "@/lib/api";
import { ApiFailure } from "@/lib/api/errors";

const BASE_MS = 30_000;
const MAX_MS = 120_000;

export function useNotifications(enabled: boolean) {
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = BASE_MS;

    function schedule(ms: number) {
      timer = setTimeout(() => void tick(), ms);
    }

    async function tick() {
      if (stop) return;
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        schedule(delay);
        return;
      }
      try {
        const page = await api.listNotifications();
        if (stop) return;
        setItems(page.items);
        setUnread(page.items.filter((n) => !n.read_at).length);
        delay = BASE_MS;
        schedule(delay);
      } catch (err) {
        if (stop) return;
        if (err instanceof ApiFailure && err.code === "unauthorized") {
          return;
        }
        delay = Math.min(delay * 2, MAX_MS);
        schedule(delay);
      }
    }

    function onOnline() {
      delay = BASE_MS;
      if (timer) clearTimeout(timer);
      void tick();
    }

    void tick();
    window.addEventListener("online", onOnline);
    return () => {
      stop = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener("online", onOnline);
    };
  }, [enabled]);

  return { unread, items };
}
