import { useState } from "react";

import { api, unwrap } from "../api/client";
import { useMeta } from "../api/queries";
import { IconPlay, IconWarn } from "./icons";

/** Opens the map's page in osu!lazer with its difficulty picked; lazer's "Go to beatmap" button (») there jumps to it
 * in song select. Shown only when lazer was found and the map has an id on the osu! website. */
export function OpenInLazer({ beatmapId }: { beatmapId: number | null | undefined }) {
  const meta = useMeta();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!meta.data?.lazer_found || !beatmapId || beatmapId <= 0) return null;
  const open = () => {
    setBusy(true);
    setError(null);
    unwrap(api.POST("/api/exports/lazer-open", { body: { beatmap_id: beatmapId } }))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };
  return (
    <button
      type="button"
      className="btn btn--sm btn--ghost"
      disabled={busy}
      onClick={open}
      title={error ?? "Open this map in osu!lazer, then press Go to beatmap (») there"}
    >
      {error ? <IconWarn /> : <IconPlay />} in lazer
    </button>
  );
}
