import { useState } from "react";

import { useUpsertSubreddit } from "@/lib/queries";
import type { ListingSort } from "@/types/radar";

const LISTINGS: ListingSort[] = ["new", "hot", "top", "rising"];

/**
 * Alta de un subreddit vigilado.
 *
 * Solo pide lo imprescindible: el resto tiene valores por defecto en el
 * esquema, y un formulario con ocho campos para empezar a vigilar un foro
 * es una barrera, no una función.
 */
export function SubredditForm() {
  const mutation = useUpsertSubreddit();
  const [name, setName] = useState("");
  const [listing, setListing] = useState<ListingSort>("new");
  const [tags, setTags] = useState("");

  const enviar = (event: React.FormEvent) => {
    event.preventDefault();
    const limpio = name.trim();
    if (!limpio) return;

    mutation.mutate(
      {
        name: limpio,
        listing,
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      },
      {
        onSuccess: () => {
          setName("");
          setTags("");
        },
      },
    );
  };

  return (
    <form onSubmit={enviar} className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1">
        <span className="text-xs text-[--color-ink-muted]">Subreddit</span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="r/SaaS"
          className="w-40 rounded-md border border-[--color-border-subtle] bg-[--color-surface-raised] px-3 py-1.5 text-sm"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[--color-ink-muted]">Orden</span>
        <select
          value={listing}
          onChange={(event) => setListing(event.target.value as ListingSort)}
          className="rounded-md border border-[--color-border-subtle] bg-[--color-surface-raised] px-3 py-1.5 text-sm"
        >
          {LISTINGS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-[--color-ink-muted]">
          Etiquetas (separadas por comas)
        </span>
        <input
          value={tags}
          onChange={(event) => setTags(event.target.value)}
          placeholder="vertical, prioritario"
          className="w-48 rounded-md border border-[--color-border-subtle] bg-[--color-surface-raised] px-3 py-1.5 text-sm"
        />
      </label>

      <button
        type="submit"
        disabled={mutation.isPending || !name.trim()}
        className="rounded-md bg-[--color-ink] px-3 py-1.5 text-sm text-[--color-surface] disabled:opacity-50"
      >
        {mutation.isPending ? "Guardando..." : "Vigilar"}
      </button>

      {mutation.isError && (
        <p className="w-full text-xs text-[--color-urgency-critical]">
          {String(mutation.error)}
        </p>
      )}
    </form>
  );
}
