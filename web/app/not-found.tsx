import { BrandMark } from "@/components/brand/mark";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div id="main" tabIndex={-1} className="flex min-h-dvh flex-col items-center justify-center bg-bg px-6 text-center">
      <BrandMark />
      <h1 className="mt-10 font-display text-4xl text-cream">No such page.</h1>
      <p className="mt-3 max-w-md text-sm text-mist">
        The desk does not invent routes. Go back to the landing and enter through the correct door.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Button href="/">Return</Button>
        <Button href="/sign-in" variant="ghost">
          Sign in
        </Button>
      </div>
    </div>
  );
}
