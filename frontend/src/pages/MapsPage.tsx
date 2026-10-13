import { useMemo } from "react";
import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { useHideMaps, useSuggestions } from "../api/queries";
import { ExportPanel } from "../components/ExportPanel";
import { MapTable } from "../components/MapTable";
import { QueryView } from "../components/states";
import { Alert, Card, Page } from "../components/ui";
import { fmt, int } from "../lib/format";

export default function MapsPage() {
  const q = useSuggestions();
  return (
    <Page
      title="Map Suggestion"
      sub={
        q.data ? (
          <>
            Maps to practise your weakest skills, picked from {int(q.data.pool_size)} popular ranked maps around your level (
            {q.data.comfort.toFixed(1)}★). Maps you already played are left out. For a full staged playlist of one skill use{" "}
            <Link to="/skills">Skill Development</Link>.
          </>
        ) : (
          "Maps to practise your weakest skills, from the bundled pool of popular ranked maps."
        )
      }
    >
      <QueryView query={q}>{(s) => <Body s={s} />}</QueryView>
    </Page>
  );
}

function why(sec: Schemas["SuggestionSection"]): string {
  if (sec.skill === "general") return "Slightly above your level, popular maps.";
  if (sec.skill === "quadrant") return "Jumps that land in your weakest quadrant.";
  return `One of your weakest skills (score ${fmt(sec.score, 0)} of 100).`;
}

function Body({ s }: { s: Schemas["Suggestions"] }) {
  const hide = useHideMaps();
  const all = useMemo(() => s.sections.flatMap((sec) => sec.maps), [s.sections]);
  return (
    <>
      {s.sections.map((sec) => (
        <Card key={sec.skill} title={sec.title} sub={why(sec)}>
          <MapTable maps={sec.maps} onHide={(m) => hide.mutate([m.md5])} />
        </Card>
      ))}
      {s.hidden > 0 && (
        <Alert tone="info">
          <span>
            {s.hidden} map(s) you marked as not for you are never suggested.{" "}
            <button type="button" className="btn btn--sm" onClick={() => hide.mutate(null)} disabled={hide.isPending}>
              Show the {s.hidden} hidden maps again
            </button>
          </span>
        </Alert>
      )}
      {hide.isError && <Alert tone="bad">{hide.error.message}</Alert>}
      {all.length > 0 && (
        <ExportPanel
          maps={all}
          name={s.collection_name}
          preferred={s.preferred_client}
          title="Get all these maps into osu!"
          sub={`All ${all.length} suggested maps at once, as the collection “${s.collection_name}”.`}
        />
      )}
    </>
  );
}
