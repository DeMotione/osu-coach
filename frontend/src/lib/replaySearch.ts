import { useEffect, useState } from "react";

import { useCheckReplays } from "../api/queries";

const SEARCH_WAIT_MS = 250;

/** The replays a replay picker lists, and its search: the list follows each key at once (the picker filters it),
 * every replay (not only the newest) is searched once typing stops. ``path``: a replay opened elsewhere or dropped
 * (always in the list); ``onlyMap``: only the plays of its map. */
export function useReplays(path: string | null, onlyMap = false) {
  const [search, setSearch] = useState("");
  const [searched, setSearched] = useState("");
  useEffect(() => {
    const wait = setTimeout(() => setSearched(search.trim()), SEARCH_WAIT_MS);
    return () => clearTimeout(wait);
  }, [search]);
  const list = useCheckReplays(path, onlyMap, searched);
  return { search, setSearch, list, all: list.data?.replays ?? [] };
}

export type Replays = ReturnType<typeof useReplays>;
