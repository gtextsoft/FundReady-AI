import { NextRequest, NextResponse } from "next/server";
import { apiBase } from "@/lib/auth/cookies";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ startupId: string; runId: string }> },
) {
  const { startupId, runId } = await params;
  const auth = request.headers.get("authorization");
  if (!auth) {
    return NextResponse.json(
      { error: { code: "unauthorized", message: "You are signed out." } },
      { status: 401 },
    );
  }

  const upstream = await fetch(
    `${apiBase()}/v1/startups/${startupId}/audits/${runId}/report.pdf`,
    { headers: { Authorization: auth, Accept: "application/pdf" } },
  );
  if (!upstream.ok) {
    const data = await upstream.json().catch(() => null);
    return NextResponse.json(
      data ?? { error: { message: "Could not download the PDF." } },
      { status: upstream.status },
    );
  }

  return new NextResponse(await upstream.arrayBuffer(), {
    status: 200,
    headers: {
      "Content-Type": "application/octet-stream",
      "Cache-Control": "no-store",
    },
  });
}
