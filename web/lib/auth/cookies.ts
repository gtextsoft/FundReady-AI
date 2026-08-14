import type { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/api/config";

const REFRESH_COOKIE = "fr_refresh";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

export { apiBase };

export function refreshCookieName() {
  return REFRESH_COOKIE;
}

function cookieOptions(token: string | null) {
  return {
    httpOnly: true,
    path: "/",
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    ...(token
      ? { maxAge: COOKIE_MAX_AGE }
      : { maxAge: 0, expires: new Date(0) }),
  };
}

export function writeRefreshCookie(res: NextResponse, token: string | null) {
  res.cookies.set(REFRESH_COOKIE, token ?? "", cookieOptions(token));
}

export function readRefresh(request: NextRequest): string | null {
  return request.cookies.get(REFRESH_COOKIE)?.value ?? null;
}
