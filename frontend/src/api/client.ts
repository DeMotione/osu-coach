import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Job = Schemas["ScanJob"] | Schemas["AnalysisJob"] | Schemas["LazerPackJob"] | Schemas["OszJob"] | Schemas["PlayGoalJob"];

/** An error answer of the API (`{detail, code}`), or `offline` when the osu! coach server can't be reached. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const OFFLINE = "offline";

export const api = createClient<paths>({ baseUrl: "" });

function toError(status: number, body: unknown): ApiError {
  if (body && typeof body === "object" && "detail" in body) {
    const b = body as { detail: unknown; code?: unknown };
    return new ApiError(status, typeof b.code === "string" ? b.code : "error", String(b.detail));
  }
  return new ApiError(status, "error", `The request failed (${status}).`);
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** The data of an openapi-fetch call, or an {@link ApiError}. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let res: Result<T>;
  try {
    res = await call;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError(0, OFFLINE, "osu! coach isn't running. Start it again (osu-coach ui) and reload.");
  }
  if (res.error !== undefined || !res.response.ok) throw toError(res.response.status, res.error);
  return res.data as T;
}

export function isApiError(e: unknown, code?: string): e is ApiError {
  return e instanceof ApiError && (code === undefined || e.code === code);
}

/** POST a JSON body and save the file the API answers with (collection.db, .zip). */
export async function downloadFile(path: string, body: unknown, fallbackName: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError(0, OFFLINE, "osu! coach isn't running.");
  }
  if (!response.ok) throw toError(response.status, await response.json().catch(() => null));
  const blob = await response.blob();
  saveBlob(blob, filenameFrom(response.headers.get("content-disposition")) ?? fallbackName);
}

/** The file name of a Content-Disposition header (the UTF-8 one when given). */
export function filenameFrom(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      /* fall back to the plain name */
    }
  }
  const plain = /filename="([^"]+)"/i.exec(header);
  return plain ? plain[1] : null;
}

export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
