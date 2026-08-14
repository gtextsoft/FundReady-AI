import { NextRequest, NextResponse } from "next/server";
import { apiBase, writeRefreshCookie } from "@/lib/auth/cookies";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const upstream = await fetch(`${apiBase()}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    return NextResponse.json(data ?? { error: { message: "Login failed." } }, {
      status: upstream.status,
    });
  }

  if (data?.status === "authenticated" && data.tokens?.refresh_token) {
    const res = NextResponse.json({
      status: "authenticated",
      access_token: data.tokens.access_token,
      expires_in: data.tokens.expires_in,
    });
    writeRefreshCookie(res, data.tokens.refresh_token);
    return res;
  }

  return NextResponse.json(data, { status: 200 });
}
