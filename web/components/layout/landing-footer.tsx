import Link from "next/link";
import { BrandMark } from "@/components/brand/mark";

const LINKS = [
  { href: "/pricing", label: "Pricing" },
  { href: "/faq", label: "FAQ" },
  { href: "/legal/terms", label: "Terms" },
  { href: "/legal/privacy", label: "Privacy" },
];

export function LandingFooter() {
  return (
    <footer className="mx-auto grid max-w-[1184px] items-center gap-4 px-5 py-10 text-[11px] text-mist-2 md:grid-cols-3 md:px-7">
      <BrandMark />
      <p>AI-assisted investment readiness for ambitious founders.</p>
      <div className="flex flex-col gap-2 md:items-end">
        <nav className="flex flex-wrap gap-3">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-cream">
              {l.label}
            </Link>
          ))}
        </nav>
        <small>© 2026 Fundready. Decision support, not investment advice.</small>
      </div>
    </footer>
  );
}
