import { after, NextRequest, NextResponse } from "next/server";
import { apiBase, readRefresh, writeRefreshCookie } from "@/lib/auth/cookies";

export async function POST(request: NextRequest) {
  const refresh = readRefresh(request);
  const res = NextResponse.json({ ok: true });
  writeRefreshCookie(res, null);

  if (refresh) {
    const token = refresh;
    after(() => {
      void fetch(`${apiBase()}/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      }).catch(() => undefined);
    });
  }

  return res;
}
