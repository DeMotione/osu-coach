import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        // answers like 409 "nothing analysed yet" are final; only network trouble is worth another try
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400) && count < 2,
      },
    },
  });
}
