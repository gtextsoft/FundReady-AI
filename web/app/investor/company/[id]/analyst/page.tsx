"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { ChatThread, type ChatTurn } from "@/components/ui/chat-thread";
import { api } from "@/lib/api";

export default function AnalystPage() {
  const { id } = useParams<{ id: string }>();
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);

  return (
    <ChatThread
      title="Analyst"
      description="Retrieval is summary-tier only. The model cannot see a full report from this chat."
      emptyHint="Ask about sector, stage, or what the summary card actually claims."
      prompts={["What is the fundability case in one paragraph?", "What should I diligence first?"]}
      history={history}
      busy={busy}
      backHref={`/investor/company/${id}`}
      onSend={async (message) => {
        const next: ChatTurn[] = [...history, { id: crypto.randomUUID(), role: "user", content: message }];
        setHistory(next);
        setBusy(true);
        try {
          const res = await api.chatAnalyst(
            id,
            message,
            next.filter((t) => t.role !== "system").map((t) => ({ role: t.role, content: t.content })),
          );
          setHistory([...next, { id: crypto.randomUUID(), role: "assistant", content: res.reply }]);
        } catch (err) {
          setHistory([
            ...next,
            { id: crypto.randomUUID(), role: "system", content: err instanceof Error ? err.message : "No answer." },
          ]);
        } finally {
          setBusy(false);
        }
      }}
    />
  );
}
