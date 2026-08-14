"use client";

import { PageHeader } from "@/components/ui/page-header";
import { MetaList, MetaRow, Panel } from "@/components/ui/panel";
import { useSession } from "@/stores/session";

export default function AdminProfilePage() {
  const session = useSession((s) => s.session);
  return (
    <div className="max-w-xl space-y-6">
      <PageHeader title="Account" description="Admin console identity. MFA is required for every action." />
      <Panel>
        <MetaList>
          <MetaRow label="Name">{session?.displayName}</MetaRow>
          <MetaRow label="Email">{session?.email}</MetaRow>
          <MetaRow label="Role">Admin</MetaRow>
          <MetaRow label="MFA">{session?.mfaEnabled ? "Enrolled" : "Required"}</MetaRow>
        </MetaList>
      </Panel>
    </div>
  );
}
