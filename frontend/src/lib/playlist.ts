/** How many maps of a playlist stage are shown (and exported) at a time. */
export const STAGE_SIZE = 5;

/** The ``round``-th group of ``size`` maps of a ranked list, starting over after the last one (that group may be
 * shorter); ``first`` is the 0-based index of its first map. */
export function stageMaps<T>(maps: T[], round: number, size = STAGE_SIZE): { maps: T[]; first: number } {
  if (!maps.length) return { maps: [], first: 0 };
  const groups = Math.ceil(maps.length / size);
  const first = (((round % groups) + groups) % groups) * size;
  return { maps: maps.slice(first, first + size), first };
}
