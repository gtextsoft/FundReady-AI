export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow ? (
          <p className="text-[10px] font-extrabold tracking-[0.16em] text-text-faint uppercase">{eyebrow}</p>
        ) : null}
        <h1
          className={
            eyebrow
              ? "mt-1.5 text-[28px] font-semibold tracking-[-0.03em] text-cream"
              : "text-[28px] font-semibold tracking-[-0.03em] text-cream"
          }
        >
          {title}
        </h1>
        {description ? <p className="mt-1.5 max-w-2xl text-sm text-mist">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}
