import { NextRequest, NextResponse } from "next/server";
import { refreshCookieName } from "@/lib/auth/cookies";

const AUTH_PATHS = [
  "/sign-in",
  "/sign-up",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/mfa",
];

const PROTECTED_PREFIXES = ["/founder", "/investor", "/admin", "/onboarding", "/assessment", "/results"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasRefresh = Boolean(request.cookies.get(refreshCookieName())?.value);
  const isAuth = AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  const isProtected = PROTECTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  if (isProtected && !hasRefresh) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (isAuth && hasRefresh && pathname !== "/mfa" && pathname !== "/verify-email") {
    // Layouts decide the home by role after restore. Stay on auth if they
    // still need MFA or email confirmation.
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/founder/:path*",
    "/investor/:path*",
    "/admin/:path*",
    "/onboarding",
    "/assessment",
    "/results",
    "/sign-in",
    "/sign-up",
    "/forgot-password",
    "/reset-password",
    "/verify-email",
    "/mfa",
  ],
};
