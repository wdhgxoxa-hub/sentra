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
          className="rounded-md bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-ink-soft transition-colors hover:bg-accent-soft hover:text-accent"
        >
          r/{name}
        </span>
      ))}
      {rest > 0 && (
        <span
          className="text-[11px] text-ink-faint"
          title={subreddits.slice(max).map((name) => `r/${name}`).join(", ")}
        >
          +{rest}
        </span>
      )}
    </div>
  );
}
