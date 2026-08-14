import { BrandMark } from "@/components/brand/mark";
import Link from "next/link";
import { Suspense } from "react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative grid min-h-dvh place-items-center bg-bg px-6 py-16">
      <Link href="/" className="absolute left-8 top-7">
        <BrandMark />
      </Link>
      <div id="main" tabIndex={-1} className="w-full max-w-[460px] border border-line bg-surface p-10 shadow-[0_24px_70px_rgb(23_39_27_/_0.1)]">
        <Suspense fallback={<p className="text-mist">Loading…</p>}>{children}</Suspense>
      </div>
    </div>
  );
}
