import { useMemo, useState } from "react";

import type { Schemas } from "../api/client";
import { useHideMaps, useSuggestions } from "../api/queries";
import { ExportPanel } from "../components/ExportPanel";
import { MapTable } from "../components/MapTable";
import { StageNav } from "../components/StageNav";
import { QueryView } from "../components/states";
import { Alert, Card, Field, Page } from "../components/ui";
import { STAGE_SIZE, stageMaps, useRounds } from "../lib/playlist";
import { speedFitNotice } from "../lib/recommendationFit";

export default function MapsPage() {
  const [options, setOptions] = useState<{ kappa?: number; min_relevance?: number }>({});
  const q = useSuggestions(options);
  return (
    <Page title="Skill Development">
      <QueryView query={q}>{(s) => <Body s={s} options={options} onApply={setOptions} />}</QueryView>
    </Page>
  );
}

function Body({ s, options, onApply }: {
  s: Schemas["Suggestions"];
  options: object;
  onApply: (options: { kappa: number; min_relevance: number }) => void;
}) {
  const hide = useHideMaps();
  const [kappa, setKappa] = useState("0.5");
  const [relevance, setRelevance] = useState("0.3");
  const valid = kappa.trim() !== "" && relevance.trim() !== "" && Number.isFinite(Number(kappa)) &&
    Number(kappa) >= 0 && Number.isFinite(Number(relevance)) && Number(relevance) >= 0 && Number(relevance) <= 1;
  // which group of five each skill shows: back to the best ones when new settings are applied, not when a map is hidden
  const { rounds, move } = useRounds(options);
  const shown = useMemo(
    () => new Map(s.sections.map((sec) => [sec.skill, stageMaps(sec.maps, rounds(sec.skill).at)])),
    [s.sections, rounds],
  );
  // the export takes the maps on screen: five per skill
  const all = useMemo(
    () => [...new Map([...shown.values()].flatMap((g) => g.maps).map((m) => [m.md5, m])).values()],
    [shown],
  );
  return (
    <>
      <Card title="Tune your suggestions" hint="Weak skills and player ratings come from your replay analysis. Results update when you apply these values.">
        <div className="controls">
          <Field label="Skill star adjustment κₛ (stars)">
            <input className="input" type="number" min="0" step="0.1" value={kappa} onChange={(e) => setKappa(e.target.value)} />
          </Field>
          <Field label="Minimum target-skill relevance">
            <input className="input" type="number" min="0" max="1" step="0.05" value={relevance} onChange={(e) => setRelevance(e.target.value)} />
          </Field>
          <button type="button" className="btn" disabled={!valid} onClick={() => onApply({ kappa: Number(kappa), min_relevance: Number(relevance) })}>Show maps</button>
        </div>
      </Card>
      {!s.has_profile ? <Alert tone="info">Analyze replays to measure weak skills before map suggestions can be made.</Alert> :
        !s.sections.length ? <Alert tone="info">No measured skill is below the expected level (45/100 or less), so there are no weakness-based suggestions.</Alert> : null}
      {!!s.unmeasured_skills?.length && <p className="small muted">Unmeasured skills are not selected: {s.unmeasured_skills.join(", ")}.</p>}
      {s.sections.map((sec) => {
        const { maps, first } = shown.get(sec.skill) ?? { maps: [], first: 0 };
        const fitNotice = sec.skill === "speed" ? speedFitNotice(maps, sec.target_demand) : null;
        return (
          <Card
            className="map-suggestion-card"
            key={sec.skill}
            title={sec.title}
            hint={`${sec.eligible} comfort-level maps · adjusted ${sec.skill_adjusted_stars?.toFixed(2) ?? "unknown"}★ · target ${sec.target_stars?.toFixed(2) ?? "unknown"}★ · demand ${sec.target_demand?.toFixed(1) ?? "unknown"}`}
            actions={
              sec.maps.length > STAGE_SIZE && (
                <StageNav rounds={rounds(sec.skill)} first={first} count={maps.length} total={sec.maps.length} onMove={(to) => move(sec.skill, to)} />
              )
            }
          >
            {fitNotice && <Alert tone="warn">{fitNotice}</Alert>}
            <MapTable key={`${sec.skill}:${sec.eligible}:${maps[0]?.md5 ?? ""}:${sec.skill_adjusted_stars}`} maps={maps} onHide={(m) => hide.mutate([m.md5])} />
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
          sub={`The ${all.length} maps shown above at once, as the collection “${s.collection_name}”.`}
        />
      )}
    </>
  );
}
