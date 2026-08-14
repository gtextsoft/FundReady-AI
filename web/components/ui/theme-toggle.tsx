"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "fundready.theme";

export function useColorScheme() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const next = localStorage.getItem(STORAGE_KEY) === "dark";
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
  }

  return { dark, toggle };
}

export function ThemeToggle({ className }: { className?: string }) {
  const { dark, toggle } = useColorScheme();

  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        "flex h-11 w-11 cursor-pointer items-center justify-center text-mist hover:text-cream",
        className,
      )}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      aria-pressed={dark}
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
