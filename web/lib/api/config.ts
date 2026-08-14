const PRODUCTION_API_URL = "https://fundready-ai.onrender.com";
const DEV_API_URL = "http://localhost:8000";

/**
 * Upstream FastAPI origin used by server routes and Next.js rewrites.
 * The browser never calls this directly — it hits same-origin `/v1/*`,
 * which `next.config.ts` proxies here. That keeps production working
 * without opening CORS on Render.
 */
export function apiBase(): string {
  const configured = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "").trim();
  const raw = configured || (process.env.NODE_ENV === "production" ? PRODUCTION_API_URL : DEV_API_URL);
  return raw.replace(/\/+$/, "");
}

export function assertProductionApi(url: string) {
  if (process.env.VERCEL_ENV !== "production") return;
  if (/localhost|127\.0\.0\.1/i.test(url)) {
    throw new Error(
      `Production build cannot target ${url}. Set API_URL=https://fundready-ai.onrender.com`,
    );
  }
}
