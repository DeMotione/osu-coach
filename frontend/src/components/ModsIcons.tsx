const MODS = [
  { code: "HD", name: "Hidden", icon: "/mod-hidden.svg" },
  { code: "HR", name: "Hard Rock", icon: "/mod-hard-rock.svg" },
  { code: "DT", name: "Double Time", icon: "/mod-double-time.svg" },
] as const;

/** Display the supported map mods without spending a text line in the table. */
export function ModsIcons({ mods }: { mods: string | null | undefined }) {
  if (!mods || mods === "NM") return null;
  const selected = MODS.filter(({ code }) => mods.includes(code));
  if (!selected.length || selected.map(({ code }) => code).join("").length !== mods.length) return <span>{mods}</span>;

  return (
    <span className="map-mods" role="img" aria-label={selected.map(({ name }) => name).join(", ")}>
      {selected.map(({ code, icon }) => <img key={code} src={icon} alt="" width="25" height="18" />)}
    </span>
  );
}
