import { Children, useId, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { int } from "../lib/format";
import { IconCheck, IconHelp, IconInfo, IconUpload, IconWarn } from "./icons";

// ------------------------------------------------------------------ page structure
/** A page. Its title is a heading for screen readers only: the sidebar and the toolbar show which page this is. */
export function Page({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="page">
      <h1 className="visually-hidden">{title}</h1>
      {children}
    </div>
  );
}

interface CardProps {
  title?: ReactNode;
  /** What the card shows and how it is calculated: a "?" next to the title that shows it on hover / focus. */
  hint?: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  foot?: ReactNode;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function Card({ title, hint, sub, actions, foot, children, className, style }: CardProps) {
  return (
    <section className={className ? `card ${className}` : "card"} style={style}>
      {(title || actions) && (
        <div className="card__head">
          <div>
            {title && (
              <h2 className="card__title">
                {title}
                {hint && <Hint text={hint} />}
              </h2>
            )}
            {sub && <p className="card__sub">{sub}</p>}
          </div>
          {actions && <div className="card__actions">{actions}</div>}
        </div>
      )}
      <div className="card__body">{children}</div>
      {foot && <div className="card__foot">{foot}</div>}
    </section>
  );
}

/** Two equal cards side by side (one column on narrow screens). Exactly two children, so no half row. */
export function Row({ children }: { children: [ReactNode, ReactNode] }) {
  return <div className="row">{children}</div>;
}

export type TileCount = 1 | 2 | 3 | 4 | 6 | 8;

/** Equal tiles; the count is one whose columns divide evenly at every width. */
export function Tiles({ n, children }: { n: TileCount; children: ReactNode }) {
  const count = Children.toArray(children).length;
  if (import.meta.env.DEV && count !== n) console.warn(`<Tiles n={${n}}> got ${count} tiles`);
  return <div className={`tiles tiles--${n}`}>{children}</div>;
}

export function Section({ title, children }: { title?: ReactNode; children: ReactNode }) {
  return (
    <div className="section">
      {title && <h3 className="section__title">{title}</h3>}
      {children}
    </div>
  );
}

// ------------------------------------------------------------------ values
export function Hint({ text }: { text: ReactNode }) {
  return (
    <span className="hint" tabIndex={0} role="note" aria-label={typeof text === "string" ? text : undefined}>
      <IconHelp />
      <span className="hint__bubble">{text}</span>
    </span>
  );
}

export function Delta({ value, text, invert = false }: { value: number | null | undefined; text: string; invert?: boolean }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const up = invert ? value < 0 : value > 0;
  const kind = value === 0 ? "flat" : up ? "up" : "down";
  return <span className={`delta delta--${kind}`}>{text}</span>;
}

interface StatProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  note?: ReactNode;
}

export function Stat({ label, value, hint, note }: StatProps) {
  return (
    <div className="stat">
      <div className="stat__label">
        <span>{label}</span>
        {hint && <Hint text={hint} />}
      </div>
      <div className="stat__value">{value}</div>
      {note && <div className="stat__note">{note}</div>}
    </div>
  );
}

export function Badge({ tone, children }: { tone: "bad" | "warn" | "good" | "info" | "muted"; children: ReactNode }) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function Meter({ value, color }: { value: number; color: string }) {
  return (
    <div className="meter" aria-hidden="true">
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
    </div>
  );
}

export function Alert({ tone = "info", children }: { tone?: "info" | "good" | "warn" | "bad"; children: ReactNode }) {
  const Icon = tone === "good" ? IconCheck : tone === "info" ? IconInfo : IconWarn;
  return (
    <div className={`alert alert--${tone}`} role={tone === "bad" ? "alert" : "status"}>
      <Icon />
      <div className="alert__body">{children}</div>
    </div>
  );
}

export function Progress({ value, text, right }: { value: number | null | undefined; text?: ReactNode; right?: ReactNode }) {
  const known = value !== null && value !== undefined && Number.isFinite(value);
  return (
    <div className="progress">
      <div
        className={known ? "progress__bar" : "progress__bar indeterminate"}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={known ? Math.round((value as number) * 100) : undefined}
      >
        <span className="progress__fill" style={{ width: `${known ? (value as number) * 100 : 35}%` }} />
      </div>
      {(text || right) && (
        <div className="progress__text">
          <span>{text}</span>
          {right && <span className="num">{right}</span>}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ controls
export function Field({ label, hint, help, children }: { label: ReactNode; hint?: ReactNode; help?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field__label">
        {label}
        {hint && <Hint text={hint} />}
      </span>
      {children}
      {help && <span className="field__help">{help}</span>}
    </label>
  );
}

export interface Option<T> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
  /** Shown when pointing at the option (e.g. why it is disabled). */
  title?: string;
}

export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
  block = false,
}: {
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  block?: boolean;
}) {
  const name = useId();
  const cls = ["segmented", block ? "segmented--block" : ""].filter(Boolean).join(" ");
  return (
    <div className={cls} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <label
          key={String(o.value)}
          className={`segmented__option${o.value === value ? " checked" : ""}${o.disabled ? " disabled" : ""}`}
          title={o.title}
        >
          <input
            type="radio"
            name={name}
            checked={o.value === value}
            disabled={o.disabled}
            onChange={() => onChange(o.value)}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
  hint?: ReactNode;
}) {
  return (
    <label className="switch">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch__track" />
      <span>{label}</span>
      {hint && <Hint text={hint} />}
    </label>
  );
}

export function Pills<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string; color?: string }[];
  value: T[];
  onChange: (v: T[]) => void;
  label: string;
}) {
  return (
    <div className="pills" role="group" aria-label={label}>
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <button
            key={o.value}
            type="button"
            className="pill"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])}
          >
            {o.color && <span className="pill__dot" style={{ background: o.color }} />}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: ReactNode }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          role="tab"
          className="tab"
          aria-selected={t.value === value}
          onClick={() => onChange(t.value)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Dropzone({
  accept,
  multiple = true,
  onFiles,
  title,
  help,
}: {
  accept: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
  title: ReactNode;
  help?: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const exts = accept.split(",").map((s) => s.trim().toLowerCase());
  const keep = (files: FileList | null) =>
    Array.from(files ?? []).filter((f) => exts.some((x) => f.name.toLowerCase().endsWith(x)));
  return (
    <div
      className={over ? "dropzone over" : "dropzone"}
      role="button"
      tabIndex={0}
      onClick={() => input.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const files = keep(e.dataTransfer.files);
        if (files.length) onFiles(multiple ? files : files.slice(0, 1));
      }}
    >
      <IconUpload width={22} height={22} />
      <span>
        <strong>{title}</strong>
      </span>
      {help && <span className="small">{help}</span>}
      <input
        ref={input}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(e) => {
          const files = keep(e.target.files);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

/**
 * The files added with a {@link Dropzone}, as chips: only the first ``max`` by name and then how many more, so a big
 * drop of replays doesn't stretch the card.
 */
export function FileChips({ files, max = 15 }: { files: { id: string; name: string; path: string }[]; max?: number }) {
  if (!files.length) return null;
  const more = files.length - max;
  return (
    <div className="file-list">
      {files.slice(0, max).map((f) => (
        <span key={f.id} className="chip" title={f.path}>
          {f.name}
        </span>
      ))}
      {more > 0 && <span className="chip chip--more">and {int(more)} more</span>}
    </div>
  );
}
