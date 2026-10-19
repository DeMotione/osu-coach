import { useId, useState, type ReactNode } from "react";

import { useAddInstall, useInstalls } from "../../api/queries";
import { IconOsu, IconTriangles } from "../icons";
import type { Setup, SetupPatch } from "../SetupForm";
import { Alert } from "../ui";
import { ChoiceCards, Step } from "./parts";

type Client = Setup["client"];

const NAME: Record<Client, string> = { stable: "osu!stable", lazer: "osu!lazer" };
const WINDOWS = typeof navigator !== "undefined" && /windows/i.test(navigator.userAgent);
const PLACEHOLDER: Record<Client, string> = WINDOWS
  ? { stable: "C:\\Users\\you\\AppData\\Local\\osu!", lazer: "C:\\Users\\you\\AppData\\Roaming\\osu" }
  : { stable: "~/.local/share/osu-wine/osu!", lazer: "~/.local/share/osu" };
const WHERE: Record<Client, string> = {
  stable: "The folder osu!.exe is in, with the Songs folder next to it (right-click the osu! shortcut → Open file location).",
  lazer: "osu!lazer's data folder, with files and client.realm in it. The Open osu! folder button in osu!lazer's settings opens it.",
};

/** Step 1: which osu! the player uses, and where it is when it wasn't found. */
export function ClientStep({ setup, onChange, foot }: { setup: Setup; onChange: (patch: SetupPatch) => void; foot: ReactNode }) {
  const installs = useInstalls();
  const client = setup.client;
  const found = (installs.data ?? []).filter((i) => i.kind === client);
  const [elsewhere, setElsewhere] = useState(false);
  return (
    <Step
      title="Which osu! do you play?"
      sub="osu! coach reads the replays osu! saves of your plays. Tell it which osu! you use, and it looks for it on this computer."
      foot={foot}
    >
      <ChoiceCards
        label="osu! version"
        value={client}
        onChange={(v) => onChange({ client: v })}
        options={[
          { value: "stable", title: "osu!stable", text: "The classic client (osu!.exe). It keeps a replay of every play you finish.", icon: <IconOsu /> },
          { value: "lazer", title: "osu!lazer", text: "The new client. osu! coach reads its replays straight from its data folder.", icon: <IconTriangles /> },
        ]}
      />
      {installs.isPending ? (
        <p className="muted small">Looking for osu! on this computer…</p>
      ) : found.length > 0 ? (
        <>
          <Alert tone="good">
            Found {found.length === 1 ? NAME[client] : `${found.length} installs of ${NAME[client]}`}:{" "}
            {found.map((i, n) => (
              <span key={i.root}>
                {n > 0 && ", "}
                <code className="path">{i.root}</code>
              </span>
            ))}
          </Alert>
          {elsewhere ? (
            <FolderForm key={client} client={client} />
          ) : (
            <button type="button" className="btn btn--ghost btn--sm onboarding__aside" onClick={() => setElsewhere(true)}>
              Is {NAME[client]} somewhere else too?
            </button>
          )}
        </>
      ) : (
        <>
          <Alert tone="info">
            {NAME[client]} wasn't found automatically. Enter the folder it is in — or skip this: you can add replay files
            yourself in step 3.
          </Alert>
          <FolderForm key={client} client={client} />
        </>
      )}
    </Step>
  );
}

function FolderForm({ client }: { client: Client }) {
  const id = useId();
  const add = useAddInstall();
  const [path, setPath] = useState("");
  return (
    <form
      className="field"
      onSubmit={(e) => {
        e.preventDefault();
        if (path.trim()) add.mutate(path.trim());
      }}
    >
      <label className="field__label" htmlFor={id}>
        {NAME[client]} folder
      </label>
      <div className="input-row">
        <input
          id={id}
          className="input"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder={PLACEHOLDER[client]}
          spellCheck={false}
          autoComplete="off"
        />
        <button type="submit" className="btn" disabled={!path.trim() || add.isPending}>
          {add.isPending ? "Checking…" : "Check folder"}
        </button>
      </div>
      <span className="field__help">{WHERE[client]}</span>
      {add.isError && <Alert tone="bad">{add.error.message}</Alert>}
      {add.isSuccess && (
        <Alert tone="good">
          Found {NAME[add.data.kind]} in <code className="path">{add.data.root}</code>. Its replays will be read in step 3.
        </Alert>
      )}
    </form>
  );
}
