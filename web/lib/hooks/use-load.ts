"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiFailure } from "@/lib/api/errors";

export type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "empty" }
  | { status: "ready"; data: T };

export function useLoad<T>(
  fn: () => Promise<T>,
  deps: unknown[] = [],
  isEmpty: (data: T) => boolean = () => false,
): LoadState<T> & { reload: () => Promise<void> } {
  const [state, setState] = useState<LoadState<T>>({ status: "loading" });
  const fnRef = useRef(fn);
  const isEmptyRef = useRef(isEmpty);
  const key = JSON.stringify(deps);

  useEffect(() => {
    fnRef.current = fn;
    isEmptyRef.current = isEmpty;
  });

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const data = await fnRef.current();
      setState(isEmptyRef.current(data) ? { status: "empty" } : { status: "ready", data });
    } catch (err) {
      setState({
        status: "error",
        message: err instanceof ApiFailure ? err.message : err instanceof Error ? err.message : "Could not load.",
      });
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload, key]);

  return { ...state, reload };
}
