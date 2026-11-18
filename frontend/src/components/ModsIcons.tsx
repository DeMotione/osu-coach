const MODS = [
  { code: "DT", name: "Double Time", icon: "/mod-double-time.svg" },
  { code: "HD", name: "Hidden", icon: "/mod-hidden.svg" },
  { code: "HR", name: "Hard Rock", icon: "/mod-hard-rock.svg" },
] as const;

const shownRate = (rate: number) => `${rate.toFixed(2)}×`;

/** Display the supported map mods and any custom speed in the Mods column; hovering an icon names its mod. */
export function ModsIcons({ mods, rate = 1 }: { mods: string | null | undefined; rate?: number }) {
  const speed = Number.isFinite(rate) && rate !== 1 ? shownRate(rate) : null;
  if (!mods || mods === "NM") return speed ? <span className="map-mods__rate-only">{speed}</span> : null;

  const selected = MODS.filter(({ code }) => mods.includes(code));
  if (!selected.length || selected.map(({ code }) => code).join("").length !== mods.length) {
    return <span>{mods}{speed ? ` · ${speed}` : ""}</span>;
  }

  const customDt = mods.includes("DT") && speed !== null && Math.round(rate * 100) !== 150;
  const label = selected.map(({ name, code }) => code === "DT" && customDt ? `${name} ${speed}` : name).join(", ");
  return (
    <span className="map-mods" role="img" aria-label={speed && !mods.includes("DT") ? `${label}, ${speed}` : label}>
      {selected.map(({ code, name, icon }) => {
        // each mod has its place (map-mods__dt / __hd / __hr), so a table can line every one up under the others
        const slot = `map-mods__${code.toLowerCase()}`;
        const badge = code === "DT" && customDt;
        const img = <img key={code} className={badge ? undefined : slot} src={icon} alt="" title={name} width="25" height="20" />;
        // a DT rate other than 1.50× rides on the DT icon, so it reads as that mod's speed
        return badge ? (
          <span key={code} className={`map-mods__badge ${slot}`} title={`${name} ${speed}`}>
            {img}
            <span className="map-mods__badge-rate" aria-hidden="true">{speed}</span>
          </span>
        ) : img;
      })}
      {speed && !mods.includes("DT") && <span className="map-mods__rate-only map-mods__dt" aria-hidden="true">{speed}</span>}
    </span>
  );
}
