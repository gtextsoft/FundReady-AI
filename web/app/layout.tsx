import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Source_Sans_3 } from "next/font/google";
import { AuthProvider } from "@/components/providers/auth-provider";
import { ThemedToaster } from "@/components/ui/toaster";
import { PRODUCTION_APP_URL } from "@/lib/api/config";
import "./globals.css";

const sourceSans = Source_Sans_3({
  subsets: ["latin"],
  variable: "--font-source",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_APP_URL ??
      (process.env.VERCEL_ENV === "production" ? PRODUCTION_APP_URL : "http://localhost:3000"),
  ),
  title: "FundReady — Investment Readiness Audit",
  description:
    "A rigorous, evidence-weighted audit that shows founders whether their business is ready for investment.",
  icons: {
    icon: [{ url: "/logo.png", type: "image/png" }],
    apple: [{ url: "/apple-icon.png", type: "image/png" }],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`h-full ${sourceSans.variable} ${fraunces.variable} ${plexMono.variable}`}>
      <body className="min-h-full bg-bg font-sans text-cream antialiased">
        <a href="#main" className="sr-only left-4 top-4 z-50 bg-brand px-4 py-2 text-white">
          Skip to content
        </a>
        <AuthProvider>
          {children}
          <ThemedToaster />
        </AuthProvider>
      </body>
    </html>
  );
}
