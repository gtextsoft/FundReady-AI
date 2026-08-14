"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ApiFailure } from "@/lib/api/errors";
import { AssessmentLoader } from "@/components/brand/assessment-loader";
import { BrandMark } from "@/components/brand/mark";
import { Button } from "@/components/ui/button";
import { founderNeedsOnboarding } from "@/lib/domain/onboarding";

function copyFor(status: string) {
  if (status === "queued") return "In the queue. The scorer is picking this up…";
  if (status === "running") return "The model is scoring the file.";
  return "Fundready is scoring the file.";
}

export default function AssessmentPage() {
  const router = useRouter();
  const [message, setMessage] = useState("Queuing the audit…");
  const [failed, setFailed] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (failed) return;
    let stop = false;
    void (async () => {
      try {
        const profile = await api.getProfile();
        if (founderNeedsOnboarding(profile)) {
          router.replace("/onboarding");
          return;
        }
        const run = await api.requestAudit(profile.id);
        setMessage(copyFor(run.status));
        const started = Date.now();
        while (!stop && Date.now() - started < 5 * 60_000) {
          const current = await api.getAudit(profile.id, run.id);
          if (current.status === "succeeded" || current.status === "failed") {
            router.replace("/results");
            return;
          }
          setMessage(copyFor(current.status));
          await new Promise((r) => setTimeout(r, 3000));
        }
        if (!stop) {
          setTimedOut(true);
          setMessage("Still running. You can wait on the results page or return to the desk.");
        }
      } catch (err) {
        if (err instanceof ApiFailure && err.code === "not_found") {
          router.replace("/onboarding");
          return;
        }
        setFailed(true);
        setMessage("Could not queue the audit. Check the profile and try again.");
      }
    })();
    return () => {
      stop = true;
    };
  }, [router, failed]);

  const waiting = !failed && !timedOut;

  return (
    <div id="main" tabIndex={-1} className="flex min-h-dvh flex-col items-center justify-center bg-bg px-6 text-center">
      {waiting ? (
        <AssessmentLoader message={message} />
      ) : (
        <>
          <BrandMark />
          <h1 className="mt-10 font-display text-4xl text-cream">Assessment in motion.</h1>
          <p className="mt-4 max-w-md text-sm text-mist">{message}</p>
        </>
      )}
      <div className="mt-10 flex flex-wrap justify-center gap-3">
        {failed ? (
          <Button type="button" onClick={() => { setFailed(false); setMessage("Queuing the audit…"); }}>
            Try again
          </Button>
        ) : null}
        {timedOut ? <Button href="/results">Open results</Button> : null}
        <Button href="/founder" variant="ghost">
          Back to the desk
        </Button>
      </div>
    </div>
  );
}
