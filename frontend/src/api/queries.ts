/** Data hooks: one per endpoint, with the query keys they share. */
import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { ApiError, api, unwrap, type Schemas } from "./client";

export const keys = {
  meta: ["meta"] as const,
  health: ["health"] as const,
  settings: ["settings"] as const,
  setup: ["setup"] as const,
  installs: ["installs"] as const,
  library: ["library"] as const,
  selection: ["selection"] as const,
  analysis: ["analysis"] as const,
  profile: ["profile"] as const,
  check: ["check"] as const,
  progress: ["progress"] as const,
  goals: ["goals"] as const,
  maps: ["maps"] as const,
  playlists: ["playlists"] as const,
  exports: ["exports"] as const,
};

/** Everything that is built from the analysed replays. */
export function invalidateResults(qc: QueryClient): Promise<void> {
  return Promise.all(
    [keys.profile, keys.analysis, keys.progress, keys.goals, keys.maps, keys.playlists, keys.exports, keys.check].map(
      (queryKey) => qc.invalidateQueries({ queryKey }),
    ),
  ).then(() => undefined);
}

export function invalidateLibrary(qc: QueryClient): Promise<void> {
  return Promise.all([keys.library, keys.selection, keys.check].map((queryKey) => qc.invalidateQueries({ queryKey }))).then(
    () => undefined,
  );
}

// ------------------------------------------------------------------ system and settings
export const useMeta = () =>
  useQuery({ queryKey: keys.meta, queryFn: () => unwrap(api.GET("/api/meta")), staleTime: Infinity });

export const useHealth = () =>
  useQuery({
    queryKey: keys.health,
    queryFn: () => unwrap(api.GET("/api/health")),
    refetchInterval: (q) => (q.state.status === "error" ? 3000 : 30000),
    retry: false,
  });

export const useSettings = () =>
  useQuery({ queryKey: keys.settings, queryFn: () => unwrap(api.GET("/api/settings")), staleTime: 60_000 });

type SettingsPatch = Schemas["SettingsPatch"];

/** Change remembered choices; choices the profile depends on rebuild every page. */
export function usePatchSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: SettingsPatch) => unwrap(api.PATCH("/api/settings", { body: patch })),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: keys.settings });
      const before = qc.getQueryData<Schemas["AppSettings"]>(keys.settings);
      if (before) qc.setQueryData(keys.settings, { ...before, ...stripUndefined(patch) });
      return { before };
    },
    onError: (_e, _patch, ctx) => {
      if (ctx?.before) qc.setQueryData(keys.settings, ctx.before);
    },
    onSuccess: (settings, patch) => {
      qc.setQueryData(keys.settings, settings);
      if ("replay_set" in patch || "level_override" in patch) void invalidateResults(qc);
    },
  });
}

function stripUndefined<T extends object>(o: T): Partial<T> {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as Partial<T>;
}

export const useSetup = () => useQuery({ queryKey: keys.setup, queryFn: () => unwrap(api.GET("/api/setup")) });

export function useSaveSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (setup: Schemas["SetupUpdate"]) => unwrap(api.PUT("/api/setup", { body: setup })),
    onSuccess: (setup) => {
      qc.setQueryData(keys.setup, setup);
      void qc.invalidateQueries({ queryKey: keys.settings });
      void qc.invalidateQueries({ queryKey: keys.profile });
    },
  });
}

// ------------------------------------------------------------------ replays
export const useInstalls = () =>
  useQuery({ queryKey: keys.installs, queryFn: () => unwrap(api.GET("/api/installs")), staleTime: Infinity });

export const useLibrary = () => useQuery({ queryKey: keys.library, queryFn: () => unwrap(api.GET("/api/library")) });

export type SelectionParams = {
  player?: string | null;
  latest: Schemas["Latest"];
  date_range: Schemas["AppSettings"]["date_range"];
  date_from?: string | null;
  date_to?: string | null;
};

export const useSelection = (params: SelectionParams, enabled: boolean) =>
  useQuery({
    queryKey: [...keys.selection, params],
    queryFn: () =>
      unwrap(
        api.GET("/api/library/selection", {
          params: {
            query: {
              player: params.player ?? undefined,
              latest: params.latest,
              date_range: params.date_range,
              date_from: params.date_from ?? undefined,
              date_to: params.date_to ?? undefined,
            },
          },
        }),
      ),
    enabled,
    placeholderData: keepPreviousData,
  });

export const useAnalysisStatus = () =>
  useQuery({ queryKey: keys.analysis, queryFn: () => unwrap(api.GET("/api/analysis")) });

export async function uploadFiles(files: File[]): Promise<Schemas["UploadedFile"][]> {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  let response: Response;
  try {
    response = await fetch("/api/uploads", { method: "POST", body: form });
  } catch {
    throw new ApiError(0, "offline", "osu! coach isn't running.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, body?.code ?? "error", body?.detail ?? "Upload failed.");
  return body as Schemas["UploadedFile"][];
}

// ------------------------------------------------------------------ analysis pages
const page = <T>(name: string, fn: () => Promise<T>) =>
  ({ queryKey: [...keys.profile, name], queryFn: fn, staleTime: 5 * 60_000 }) as const;

export const useProfileSummary = (enabled = true) =>
  useQuery({ ...page("summary", () => unwrap(api.GET("/api/profile/summary"))), enabled });
export const useAnalysedReplays = (enabled = true) =>
  useQuery({ ...page("replays", () => unwrap(api.GET("/api/profile/replays"))), enabled });
export const useOverview = () => useQuery(page("overview", () => unwrap(api.GET("/api/profile/overview"))));
export const useAim = () => useQuery(page("aim", () => unwrap(api.GET("/api/profile/aim"))));
export const useTapping = () => useQuery(page("tapping", () => unwrap(api.GET("/api/profile/tapping"))));
export const useSlidersReading = () =>
  useQuery(page("sliders-reading", () => unwrap(api.GET("/api/profile/sliders-reading"))));
export const useTips = () => useQuery(page("tips", () => unwrap(api.GET("/api/profile/tips"))));
export const useClicks = (view: "screen" | "movement") =>
  useQuery({
    ...page(`clicks:${view}`, () => unwrap(api.GET("/api/profile/clicks", { params: { query: { view } } }))),
    placeholderData: keepPreviousData,
  });

// ------------------------------------------------------------------ detailed map analysis
export const useCheckReplays = (path: string | null, onlyMap: boolean) =>
  useQuery({
    queryKey: [...keys.check, "replays", path, onlyMap],
    queryFn: () =>
      unwrap(api.GET("/api/check/replays", { params: { query: { path: path ?? undefined, only_map: onlyMap } } })),
    placeholderData: keepPreviousData,
  });

export const useCheckReport = (path: string | null, online: boolean) =>
  useQuery({
    queryKey: [...keys.check, "report", path, online],
    queryFn: () => unwrap(api.POST("/api/check/report", { body: { path: path as string, online } })),
    enabled: !!path,
    staleTime: Infinity,
  });

// ------------------------------------------------------------------ progress and goals
export const useProgressPlayers = () =>
  useQuery({ queryKey: [...keys.progress, "players"], queryFn: () => unwrap(api.GET("/api/progress/players")) });

export type ProgressParams = {
  player?: string;
  period: Schemas["ProgressOut"]["period"];
  since?: string;
  until?: string;
};

export const useProgress = (params: ProgressParams, enabled = true) =>
  useQuery({
    queryKey: [...keys.progress, "periods", params],
    queryFn: () => unwrap(api.GET("/api/progress", { params: { query: params } })),
    enabled,
    placeholderData: keepPreviousData,
  });

export const useProgressPlays = (params: { player?: string; period: ProgressParams["period"]; key: string | null }) =>
  useQuery({
    queryKey: [...keys.progress, "plays", params],
    queryFn: () =>
      unwrap(
        api.GET("/api/progress/plays", {
          params: { query: { player: params.player, period: params.period, key: params.key as string } },
        }),
      ),
    enabled: !!params.key,
  });

export const useGoals = () => useQuery({ queryKey: keys.goals, queryFn: () => unwrap(api.GET("/api/goals")) });

function useGoalsMutation<V>(fn: (v: V) => Promise<Schemas["GoalsOut"]>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: (goals) => qc.setQueryData(keys.goals, goals) });
}

export const useAddGoal = () =>
  useGoalsMutation((goal: Schemas["GoalCreate"]) => unwrap(api.POST("/api/goals", { body: goal })));
export const useAddPlan = () => useGoalsMutation((_: void) => unwrap(api.POST("/api/goals/plan")));
export const useRemoveGoal = () =>
  useGoalsMutation((id: string) => unwrap(api.DELETE("/api/goals/{goal_id}", { params: { path: { goal_id: id } } })));

// ------------------------------------------------------------------ maps
export const useSuggestions = (params: { kappa?: number; min_relevance?: number } = {}) =>
  useQuery({ queryKey: [...keys.maps, "suggestions", params], queryFn: () => unwrap(api.GET("/api/maps/suggestions", { params: { query: params } })), placeholderData: keepPreviousData });

export function useHideMaps() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (md5s: string[] | null) =>
      md5s ? unwrap(api.POST("/api/maps/hidden", { body: { md5s } })) : unwrap(api.DELETE("/api/maps/hidden")),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.maps }),
  });
}

export const usePlaylist = (params: { skill?: string; assessed?: string; ratings?: string; comfort?: number; kappa?: number; min_relevance?: number; exclude_played?: boolean }) =>
  useQuery({
    queryKey: [...keys.playlists, params],
    queryFn: () => unwrap(api.GET("/api/playlists", { params: { query: params } })),
    placeholderData: keepPreviousData,
  });

export const useExportPreview = (body: Schemas["ExportRequest"] | null) =>
  useQuery({
    queryKey: [...keys.exports, "preview", body],
    queryFn: () => unwrap(api.POST("/api/exports/preview", { body: body as Schemas["ExportRequest"] })),
    enabled: !!body && body.maps.length > 0,
  });

export const useMergeStable = () =>
  useMutation({
    mutationFn: (body: Schemas["ExportRequest"]) => unwrap(api.POST("/api/exports/stable-collection", { body })),
  });
