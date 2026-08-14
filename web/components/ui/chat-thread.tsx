"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { TextArea } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

export type ChatTurn = { id: string; role: "user" | "assistant" | "system"; content: string };

export function ChatThread({
  title,
  description,
  emptyHint,
  prompts,
  history,
  busy,
  onSend,
  backHref,
}: {
  title: string;
  description: string;
  emptyHint: string;
  prompts?: string[];
  history: ChatTurn[];
  busy: boolean;
  onSend: (message: string) => Promise<void>;
  backHref?: string;
}) {
  const [message, setMessage] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [history.length]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setMessage("");
    await onSend(trimmed);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {backHref ? (
        <Button href={backHref} variant="quiet" size="sm" className="px-0">
          ← Back
        </Button>
      ) : null}
      <PageHeader title={title} description={description} />
      <Panel className="space-y-3">
        <div className="space-y-3" aria-live="polite">
          {history.length === 0 ? <p className="text-sm text-mist">{emptyHint}</p> : null}
          {history.map((t) => (
            <div
              key={t.id}
              className={cn(
                "rounded-[14px] px-4 py-3 text-sm leading-relaxed",
                t.role === "user"
                  ? "bg-rail-hover text-cream"
                  : t.role === "system"
                    ? "border-l-2 border-fail bg-fail/5 pl-4 text-fail"
                    : "border-l-2 border-brand bg-rail-promo pl-4 text-mist",
              )}
            >
              <p className="text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">
                {t.role === "user" ? "You" : t.role === "system" ? "Notice" : "Reply"}
              </p>
              <p className="mt-1 whitespace-pre-wrap">{t.content}</p>
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </Panel>
      {prompts?.length && history.length === 0 ? (
        <div className="flex flex-wrap gap-2">
          {prompts.map((p) => (
            <button
              key={p}
              type="button"
              className="min-h-11 cursor-pointer rounded-[10px] bg-rail-active px-3 py-2 text-left text-xs font-medium text-mist ring-1 ring-black/5 hover:text-cream hover:ring-brand/30 dark:ring-white/10"
              onClick={() => void send(p)}
            >
              {p}
            </button>
          ))}
        </div>
      ) : null}
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void send(message);
        }}
      >
        <TextArea
          label="Message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(message);
            }
          }}
        />
        <Button type="submit" loading={busy} disabled={!message.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
