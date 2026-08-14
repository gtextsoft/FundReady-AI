import { api, type ProfileResponse, type Session } from "@/lib/api";
import { ApiFailure } from "@/lib/api/errors";
import { landingFor } from "@/lib/utils";

export function founderNeedsOnboarding(profile: ProfileResponse | null): boolean {
  if (!profile) return true;
  return profile.missing_fields.length > 0;
}

export async function landingAfterAuth(
  session: Session,
  next?: string | null,
): Promise<string> {
  const dest = landingFor(session, next);
  if (session.role !== "founder") return dest;
  try {
    const profile = await api.getProfile();
    if (founderNeedsOnboarding(profile)) return "/onboarding";
    if (dest === "/onboarding") return "/founder";
    return dest;
  } catch (err) {
    if (err instanceof ApiFailure && err.code === "not_found") return "/onboarding";
    return dest;
  }
}
