/**
 * Comunidades donde se repite un problema.
 *
 * Se muestran hasta tres y el resto se cuenta: la lista completa de diez
 * foros ocupa dos líneas y aporta menos que el número.
 */
export function CommunityTags({
  subreddits,
  max = 3,
}: {
  subreddits: string[];
  max?: number;
}) {
  const visible = subreddits.slice(0, max);
  const rest = subreddits.length - visible.length;

  return (
    <div className="flex flex-wrap items-center gap-1">
      {visible.map((name) => (
        <span
          key={name}
          className="rounded-md bg-[--color-surface-2] px-1.5 py-0.5 font-mono text-[11px] text-[--color-ink-soft]"
        >
          r/{name}
        </span>
      ))}
      {rest > 0 && (
        <span
          className="text-[11px] text-[--color-ink-faint]"
          title={subreddits.slice(max).map((name) => `r/${name}`).join(", ")}
        >
          +{rest}
        </span>
      )}
    </div>
  );
}
