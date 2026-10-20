import { useMemo, useState } from "react";
import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { useHideMaps, useSuggestions } from "../api/queries";
import { ExportPanel } from "../components/ExportPanel";
import { MapTable } from "../components/MapTable";
import { QueryView } from "../components/states";
import { Alert, Card, Field, Page } from "../components/ui";
import { int } from "../lib/format";
import { speedFitNotice } from "../lib/recommendationFit";

export default function MapsPage() {
  const [options, setOptions] = useState<{ kappa?: number; min_relevance?: number }>({});
  const q = useSuggestions(options);
  return (
    <Page
      title="Skill Development"
      sub={
        q.data ? (
          <>
            Comfort-level maps for your measured weak skills, picked from {int(q.data.pool_size)} ranked maps. Maps in your replay dataset are excluded. To choose a skill and build a staged playlist, use{" "}
            <Link to="/skills">Goals & Training</Link>.
          </>
        ) : (
          "Comfort-level maps for your measured weak skills from the bundled ranked pool."
        )
      }
    >
      <QueryView query={q}>{(s) => <Body s={s} onApply={setOptions} />}</QueryView>
    </Page>
  );
}

function Body({ s, onApply }: { s: Schemas["Suggestions"]; onApply: (options: { kappa: number; min_relevance: number }) => void }) {
  const hide = useHideMaps();
  const [kappa, setKappa] = useState("0.5");
  const [relevance, setRelevance] = useState("0.3");
  const valid = kappa.trim() !== "" && relevance.trim() !== "" && Number.isFinite(Number(kappa)) &&
    Number(kappa) >= 0 && Number.isFinite(Number(relevance)) && Number(relevance) >= 0 && Number(relevance) <= 1;
  const all = useMemo(() => [...new Map(s.sections.flatMap((sec) => sec.maps).map((m) => [m.md5, m])).values()], [s.sections]);
  return (
    <>
      <Card title="Tune your suggestions" sub="Weak skills and player ratings come from your replay analysis. Results update when you apply these values.">
        <div className="controls">
          <Field label="Skill star adjustment κₛ (stars)">
            <input className="input" type="number" min="0" step="0.1" value={kappa} onChange={(e) => setKappa(e.target.value)} />
          </Field>
          <Field label="Minimum target-skill relevance">
            <input className="input" type="number" min="0" max="1" step="0.05" value={relevance} onChange={(e) => setRelevance(e.target.value)} />
          </Field>
          <button type="button" className="btn" disabled={!valid} onClick={() => onApply({ kappa: Number(kappa), min_relevance: Number(relevance) })}>Show maps</button>
        </div>
        <p className="small muted">These coefficients and map skill demands are experimental. Replays determine your {s.comfort.toFixed(2)}★ comfort level ({s.comfort_source}).</p>
      </Card>
      {!s.has_profile ? <Alert tone="info">Analyze replays to measure weak skills before map suggestions can be made.</Alert> :
        !s.sections.length ? <Alert tone="info">No measured skill is below the expected level (45/100 or less), so there are no weakness-based suggestions.</Alert> : null}
      {!!s.unmeasured_skills?.length && <p className="small muted">Unmeasured skills are not selected: {s.unmeasured_skills.join(", ")}.</p>}
      {s.sections.map((sec) => {
        const fitNotice = sec.skill === "speed" ? speedFitNotice(sec.maps, sec.target_demand) : null;
        return (
          <Card className="map-suggestion-card" key={sec.skill} title={sec.title} sub={`Weak skill ${sec.score?.toFixed(0) ?? "unknown"}/100 · ${sec.eligible} comfort-level maps · adjusted ${sec.skill_adjusted_stars?.toFixed(2) ?? "unknown"}★ · target ${sec.target_stars?.toFixed(2) ?? "unknown"}★ · demand ${sec.target_demand?.toFixed(1) ?? "unknown"}`}>
            {fitNotice && <Alert tone="warn">{fitNotice}</Alert>}
            <MapTable key={`${sec.skill}:${sec.eligible}:${sec.maps[0]?.md5 ?? ""}:${sec.skill_adjusted_stars}`} maps={sec.maps} onHide={(m) => hide.mutate([m.md5])} />
            {!sec.eligible && <p className="small muted">{Object.entries(sec.excluded ?? {}).map(([reason, count]) => `${reason}: ${count}`).join(" · ")}</p>}
          </Card>
        );
      })}
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
