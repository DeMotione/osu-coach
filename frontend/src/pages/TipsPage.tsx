import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { useTips } from "../api/queries";
import { QueryView } from "../components/states";
import { Alert, Badge, Card, Page } from "../components/ui";
import { Md } from "../lib/markdown";

type Tip = Schemas["TipOut"];

const SEVERITY: Record<number, [string, "bad" | "warn" | "muted"]> = {
  3: ["High impact", "bad"],
  2: ["Medium impact", "warn"],
  1: ["Nice to know", "muted"],
};

export default function TipsPage() {
  const q = useTips();
  return (
    <Page title="Tips">
      <QueryView query={q}>
        {(page) => (
          <>
            <Card
              title="Tips"
              hint="Red = biggest impact, orange = medium, grey = nice to know."
              foot={
                <>
                  What to change in your tablet area, sensitivity, offset or keys is on <Link to="/setup">Setup Tips</Link>.
                </>
              }
            >
              {page.tips.length ? (
                <div className="stack">{page.tips.map((t, i) => <TipCard key={`${t.title}-${i}`} tip={t} />)}</div>
              ) : (
                <Alert tone="good">No clear problems found in these replays. Keep playing and re-analyse later.</Alert>
              )}
            </Card>
            <Card title="Practice plan" hint="A simple daily routine built around your weakest skills.">
              <ol className="list list--steps">
                {page.practice_plan.map((s) => (
                  <li key={s}>
                    <Md>{s}</Md>
                  </li>
                ))}
              </ol>
            </Card>
          </>
        )}
      </QueryView>
    </Page>
  );
}

function TipCard({ tip }: { tip: Tip }) {
  const [label, tone] = SEVERITY[tip.severity] ?? ["", "muted"];
  return (
    <article className={`tip tip--${tip.severity}`}>
      <div className="tip__head">
        <Badge tone={tone}>{label}</Badge>
        <h3 className="tip__title">{tip.title}</h3>
        <span className="tip__category">{tip.category}</span>
      </div>
      <div className="tip__body">
        <p>{tip.evidence}</p>
        {tip.actions.length > 0 && (
          <ul className="list list--bullets">
            {tip.actions.map((a) => (
              <li key={a}>
                <Md>{a}</Md>
              </li>
            ))}
          </ul>
        )}
        {tip.settings.length > 0 && (
          <p className="small muted">
            Suggested values:{" "}
            {tip.settings.map((s, i) => (
              <span key={s.name}>
                {i > 0 && " · "}
                <code>{s.name}</code> = {s.value}
              </span>
            ))}
          </p>
        )}
      </div>
    </article>
  );
}
