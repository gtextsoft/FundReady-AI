"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select, TextArea } from "@/components/ui/field";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { PageHeader } from "@/components/ui/page-header";
import { PageSkeleton } from "@/components/ui/skeleton";
import { Panel, PanelList, PanelRow } from "@/components/ui/panel";
import { api, type Product } from "@/lib/api";
import { useLoad } from "@/lib/hooks/use-load";
import { toast } from "sonner";

export default function AdminProductsPage() {
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [kind, setKind] = useState("program");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useLoad(
    async () => {
      const page = await api.listProducts("?limit=100");
      return page.items;
    },
    [],
    (d) => d.length === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader title="Products" />
      <Panel className="grid gap-3 md:grid-cols-2">
        <Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Field label="Slug" value={slug} onChange={(e) => setSlug(e.target.value)} />
        <Select label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="program">program</option>
          <option value="mentorship">mentorship</option>
          <option value="event">event</option>
        </Select>
        <TextArea label="Description" value={description} onChange={(e) => setDescription(e.target.value)} className="md:col-span-2" />
        {formError ? <p className="text-sm text-fail md:col-span-2">{formError}</p> : null}
        <Button
          type="button"
          loading={busy}
          onClick={async () => {
            if (!title.trim() || !slug.trim()) {
              setFormError("Title and slug are required.");
              return;
            }
            setFormError(null);
            setBusy(true);
            try {
              await api.createProduct({
                kind,
                slug,
                title,
                description,
                regions: ["*"],
                gap_tags: [],
                active: true,
              });
              toast.success("Listed.");
              setTitle("");
              setSlug("");
              setDescription("");
              await load.reload();
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Could not create.");
            } finally {
              setBusy(false);
            }
          }}
        >
          Create
        </Button>
      </Panel>
      {load.status === "loading" ? <PageSkeleton /> : null}
      {load.status === "error" ? <ErrorState message={load.message} onRetry={() => void load.reload()} /> : null}
      {load.status === "empty" ? <EmptyState title="No products" body="Create a catalogue item above." /> : null}
      {load.status === "ready" ? (
        <PanelList>
          {load.data.map((p: Product) => (
            <PanelRow key={p.id} className="flex items-center justify-between">
              <div>
                <p className="text-cream">{p.title}</p>
                <p className="text-[11px] text-mist">
                  {p.kind} · {p.slug}
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={async () => {
                  await api.updateProduct(p.id, { active: !p.active });
                  await load.reload();
                }}
              >
                {p.active ? "Retire" : "Activate"}
              </Button>
            </PanelRow>
          ))}
        </PanelList>
      ) : null}
    </div>
  );
}
