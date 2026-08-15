"use client";

import Link from "next/link";
import { useState } from "react";
import { BrandMark } from "@/components/brand/mark";
import { Menu, X } from "lucide-react";

export function LandingNav() {
  const [open, setOpen] = useState(false);
  return (
    <nav className="mx-auto flex h-[82px] max-w-[1240px] items-center justify-between px-5 lg:px-7">
      <Link href="/">
        <BrandMark />
      </Link>
      <div className="hidden items-center gap-8 text-[13px] text-mist md:flex">
        <a href="/#how" className="hover:text-cream">
          How it works
        </a>
        <a href="/#checks" className="hover:text-cream">
          Audit framework
        </a>
        <Link href="/pricing" className="hover:text-cream">
          Pricing
        </Link>
        <Link href="/faq" className="hover:text-cream">
          FAQ
        </Link>
        <Link href="/sign-in" className="hover:text-cream">
          Sign in
        </Link>
        <Link href="/sign-up?role=investor" className="hover:text-cream">
          Investors
        </Link>
      </div>
      <div className="flex items-center gap-2">
        <Link
          href="/sign-up?role=founder"
          className="inline-flex min-h-11 items-center rounded-[4px] bg-brass px-4 py-3 text-sm font-bold text-white hover:bg-brass-hover sm:px-5"
        >
          Start AI audit <span className="ml-2">↗</span>
        </Link>
        <button
          type="button"
          className="flex h-11 w-11 items-center justify-center text-cream md:hidden"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
      {open ? (
        <div className="absolute left-0 right-0 top-[82px] z-20 border-b border-line bg-surface px-5 py-4 md:hidden">
          <div className="flex flex-col gap-1">
            <a href="/#how" className="min-h-11 py-3 text-sm text-cream" onClick={() => setOpen(false)}>
              How it works
            </a>
            <a href="/#checks" className="min-h-11 py-3 text-sm text-cream" onClick={() => setOpen(false)}>
              Audit framework
            </a>
            <Link href="/pricing" className="min-h-11 py-3 text-sm text-cream" onClick={() => setOpen(false)}>
              Pricing
            </Link>
            <Link href="/faq" className="min-h-11 py-3 text-sm text-cream" onClick={() => setOpen(false)}>
              FAQ
            </Link>
            <Link href="/sign-in" className="min-h-11 py-3 text-sm text-cream" onClick={() => setOpen(false)}>
              Sign in
            </Link>
            <Link href="/sign-up?role=investor" className="min-h-11 py-3 text-sm text-cream" onClick={() => setOpen(false)}>
              Investors
            </Link>
          </div>
        </div>
      ) : null}
    </nav>
  );
}
