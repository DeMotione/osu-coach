import { describe, expect, it } from "vitest";

import { ApiError, OFFLINE, filenameFrom, isApiError, unwrap } from "./client";

const res = (status: number) => new Response(null, { status });

describe("unwrap", () => {
  it("returns the data of a successful call", async () => {
    await expect(unwrap(Promise.resolve({ data: { ok: 1 }, response: res(200) }))).resolves.toEqual({ ok: 1 });
  });

  it("turns the API's error body into an ApiError with its code", async () => {
    const call = Promise.resolve({ error: { detail: "No replays analysed yet.", code: "no_profile" }, response: res(409) });
    const e = await unwrap(call).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(isApiError(e, "no_profile")).toBe(true);
    expect((e as ApiError).status).toBe(409);
    expect((e as ApiError).message).toBe("No replays analysed yet.");
  });

  it("reports a server that can't be reached as offline", async () => {
    const e = await unwrap(Promise.reject(new TypeError("Failed to fetch"))).catch((x: unknown) => x);
    expect(isApiError(e, OFFLINE)).toBe(true);
  });

  it("handles error answers without a body", async () => {
    const e = await unwrap(Promise.resolve({ error: undefined, response: res(502) })).catch((x: unknown) => x);
    expect(isApiError(e, "error")).toBe(true);
    expect((e as ApiError).status).toBe(502);
  });
});

describe("filenameFrom", () => {
  it("prefers the UTF-8 name of a Content-Disposition header", () => {
    expect(filenameFrom(`attachment; filename="osu-coach Jump aim (4,0_).zip"; filename*=UTF-8''osu-coach%20Jump%20aim%20%284%2C0%E2%98%85%29.zip`)).toBe(
      "osu-coach Jump aim (4,0★).zip",
    );
    expect(filenameFrom('attachment; filename="collection.db"')).toBe("collection.db");
    expect(filenameFrom(null)).toBeNull();
  });
});
