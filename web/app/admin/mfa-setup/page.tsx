"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { MfaEnrolForm } from "@/components/auth/mfa-enrol-form";
import { useSession } from "@/stores/session";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";

export default function AdminMfaSetupPage() {
  const router = useRouter();
  const refresh = useSession((s) => s.refresh);
  const session = useSession((s) => s.session);

  useEffect(() => {
    if (session?.mfaEnabled) router.replace("/admin");
  }, [session?.mfaEnabled, router]);

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <PageHeader
        title="Enrol a second factor."
        description="Scan the QR with your authenticator app. If the camera cannot read it, enter a code from the app."
      />
      <Panel>
        <MfaEnrolForm
          continueLabel="Open the console"
          onContinue={async () => {
            await refresh();
            router.replace("/admin");
          }}
        />
      </Panel>
    </div>
  );
}
