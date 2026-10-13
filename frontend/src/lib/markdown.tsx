/* eslint-disable react-refresh/only-export-components -- the renderer and its component belong together */
import { Fragment, type ReactNode } from "react";

/**
 * Inline Markdown of the domain's texts (**bold**, *italic*, `code`) as React elements — never as HTML,
 * so nothing in the text can inject markup.
 */
const TOKEN = /\*\*([^*]+)\*\*|\*([^*\s][^*]*?)\*|`([^`]+)`/g;

export function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    if (m[1] !== undefined) out.push(<strong key={i++}>{m[1]}</strong>);
    else if (m[2] !== undefined) out.push(<em key={i++}>{m[2]}</em>);
    else out.push(<code key={i++}>{m[3]}</code>);
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Md({ children }: { children: string }) {
  return <Fragment>{inline(children)}</Fragment>;
}
