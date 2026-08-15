import Image from "next/image";
import { cn } from "@/lib/utils";

export function Mark({ size = 30, className }: { size?: number; className?: string }) {
  return (
    <Image
      src="/logo.png"
      alt=""
      width={size}
      height={size}
      className={cn("rounded-[22%]", className)}
      aria-hidden
    />
  );
}

export function BrandMark({
  size = 30,
  inverse = false,
}: {
  size?: number;
  inverse?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", inverse ? "text-white" : "text-cream")}>
      <Mark size={size} />
      <span className="text-[22px] font-extrabold tracking-[-0.04em]">
        Fundready
        <span className={inverse ? "text-lime" : "text-brass"}>.</span>
      </span>
    </span>
  );
}
