import { NextRequest, NextResponse } from "next/server";
import { apiBase, writeRefreshCookie } from "@/lib/auth/cookies";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const upstream = await fetch(`${apiBase()}/v1/auth/mfa/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    return NextResponse.json(data ?? { error: { message: "MFA failed." } }, {
      status: upstream.status,
    });
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
