import { useId, useMemo, useRef, useState } from "react";

export interface ComboOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
}

/** A type-to-filter picker for one value out of a list. */
export function Combobox<T extends string>({ label, value, options, onChange, placeholder, disabled }: {
  label: string;
  value: T | "";
  options: ComboOption<T>[];
  onChange: (value: T) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const open = query !== null;
  const selected = options.find((o) => o.value === value);
  const shown = useMemo(() => {
    const needle = (query ?? "").trim().toLowerCase();
    return needle ? options.filter((o) => o.label.toLowerCase().includes(needle)) : options;
  }, [options, query]);

  const close = () => setQuery(null);
  const pick = (option: ComboOption<T> | undefined) => {
    if (!option || option.disabled) return;
    onChange(option.value);
    close();
    input.current?.blur();
  };
  const move = (step: number) => {
    if (!open) setQuery("");
    setActive((i) => (shown.length ? (i + step + shown.length) % shown.length : 0));
  };

  return (
    <div className="field combo">
      <span className="field__label" id={`${id}-label`}>{label}</span>
      <input
        ref={input}
        className="input"
        role="combobox"
        aria-labelledby={`${id}-label`}
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={open && shown[active] ? `${id}-${active}` : undefined}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        placeholder={placeholder}
        value={query ?? selected?.label ?? ""}
        onFocus={(e) => { setQuery(""); setActive(0); e.currentTarget.select(); }}
        onBlur={close}
        onChange={(e) => { setQuery(e.target.value); setActive(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
          else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
          else if (e.key === "Enter" && open) { e.preventDefault(); pick(shown[active]); }
          else if (e.key === "Escape" && open) { e.preventDefault(); close(); }
        }}
      />
      {open && (
        <ul className="combo__list" role="listbox" id={`${id}-list`} aria-labelledby={`${id}-label`}>
          {shown.length ? shown.map((o, i) => (
            <li key={o.value} id={`${id}-${i}`} role="option" aria-selected={o.value === value} aria-disabled={o.disabled}
              className={`combo__option${i === active ? " combo__option--active" : ""}`}
              onMouseDown={(e) => { e.preventDefault(); pick(o); }}>
              {o.label}
            </li>
          )) : <li className="combo__empty">No matches</li>}
        </ul>
      )}
    </div>
  );
}
