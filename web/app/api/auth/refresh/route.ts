import { NextRequest, NextResponse } from "next/server";
import { apiBase, readRefresh, writeRefreshCookie } from "@/lib/auth/cookies";

export async function POST(request: NextRequest) {
  const refresh = readRefresh(request);
  if (!refresh) {
    const res = NextResponse.json(
      { error: { code: "unauthorized", message: "You are signed out." } },
      { status: 401 },
    );
    writeRefreshCookie(res, null);
    return res;
  }

  const upstream = await fetch(`${apiBase()}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  const data = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    const res = NextResponse.json(
      data ?? { error: { message: "Session expired." } },
      { status: 401 },
    );
    writeRefreshCookie(res, null);
    return res;
  }

  const res = NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
  });
  if (data.refresh_token) {
    writeRefreshCookie(res, data.refresh_token);
  }
  return res;
}
