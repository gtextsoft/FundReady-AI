import { NextRequest, NextResponse } from "next/server";
import { apiBase, readRefresh, writeRefreshCookie } from "@/lib/auth/cookies";

export async function POST(request: NextRequest) {
  const refresh = readRefresh(request);
  if (!refresh) {
    // No session cookie is a normal signed-out boot, not an auth failure.
    // 204 keeps the browser console clean; the client treats it as signed out.
    const res = new NextResponse(null, { status: 204 });
    writeRefreshCookie(res, null);
    return res;
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase()}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
  } catch {
    return NextResponse.json(
      { error: { code: "service_unavailable", message: "Could not reach the API." } },
      { status: 503 },
    );
  }
  const data = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    // Drop the cookie only when the token itself was rejected. A 5xx from
    // Render would otherwise sign the user out of a still-valid session.
    if (upstream.status === 401 || upstream.status === 403) {
      const res = NextResponse.json(
        data ?? { error: { message: "Session expired." } },
        { status: 401 },
      );
      writeRefreshCookie(res, null);
      return res;
    }
    return NextResponse.json(
      data ?? { error: { message: "Could not refresh the session." } },
      { status: upstream.status },
    );
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
