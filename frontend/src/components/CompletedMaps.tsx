import type { Schemas } from "../api/client";
import { fmt, localTime, mapName } from "../lib/format";
import { DataTable } from "./DataTable";
import { IconExternal } from "./icons";
import { OpenInLazer } from "./OpenInLazer";
import { Card } from "./ui";

type Completed = Schemas["CompletedMap"];

/** The pool maps the player has finished, last finished first: where a playlist's checked maps go once it is made
 * again, so the same map isn't played twice. */
export function CompletedMaps({ maps }: { maps: Completed[] }) {
  return (
    <Card
      title={`Completed maps (${maps.length})`}
      hint="Maps of the practice pool you have finished, from your analysed and scanned replays. Playlists leave them out, so you don't play the same map twice."
    >
      <div className="completed-maps">
      <DataTable
        label="Completed maps"
        rows={maps}
        rowKey={(m) => m.md5}
        maxHeight={320}
        columns={[
          { key: "map", header: "Map", cell: (m) => mapName(m), strong: true, wrap: true },
          { key: "stars", header: "Difficulty", cell: (m) => fmt(m.stars, 2, " ★"), value: (m) => m.stars, align: "right" },
          { key: "played", header: "Finished", cell: (m) => localTime(m.played_at), value: (m) => m.played_at, align: "right" },
          {
            key: "link",
            header: "Link",
            value: () => null,
            cell: (m) => (
              <span className="map-links">
                {m.url && (
                  <a className="btn btn--sm btn--ghost btn--icon" href={m.url} target="_blank" rel="noreferrer noopener"
                    aria-label="Open on the osu! website" title="Open on the osu! website">
                    <IconExternal width={16} height={16} />
                  </a>
                )}
                <OpenInLazer beatmapId={m.beatmap_id} iconOnly />
              </span>
            ),
          },
        ]}
      />
      </div>
    </Card>
  );
}
