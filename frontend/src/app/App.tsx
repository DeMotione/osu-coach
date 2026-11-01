import { QueryClientProvider } from "@tanstack/react-query";
import { lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { JobsProvider } from "../api/jobs";
import { ThemeProvider } from "../lib/theme";
import { Layout } from "./Layout";
import { makeQueryClient } from "./queryClient";

const ReplaysPage = lazy(() => import("../pages/ReplaysPage"));
const CheckPage = lazy(() => import("../pages/CheckPage"));
const OverviewPage = lazy(() => import("../pages/OverviewPage"));
const ProgressPage = lazy(() => import("../pages/ProgressPage"));
const AimPage = lazy(() => import("../pages/AimPage"));
const TappingPage = lazy(() => import("../pages/TappingPage"));
const SlidersReadingPage = lazy(() => import("../pages/SlidersReadingPage"));
const TipsPage = lazy(() => import("../pages/TipsPage"));
const SetupTipsPage = lazy(() => import("../pages/SetupTipsPage"));
const MapsPage = lazy(() => import("../pages/MapsPage"));
const SkillsPage = lazy(() => import("../pages/SkillsPage"));
const PlayGoalsPage = lazy(() => import("../pages/PlayGoalsPage"));
const NotFoundPage = lazy(() => import("../pages/NotFoundPage"));

const queryClient = makeQueryClient();

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <JobsProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<Navigate to="/replays" replace />} />
                <Route path="replays" element={<ReplaysPage />} />
                <Route path="check" element={<CheckPage />} />
                <Route path="overview" element={<OverviewPage />} />
                <Route path="progress" element={<ProgressPage />} />
                <Route path="aim" element={<AimPage />} />
                <Route path="tapping" element={<TappingPage />} />
                <Route path="sliders-reading" element={<SlidersReadingPage />} />
                <Route path="tips" element={<TipsPage />} />
                <Route path="setup" element={<SetupTipsPage />} />
                <Route path="maps" element={<MapsPage />} />
                <Route path="skills" element={<SkillsPage />} />
                <Route path="play-goals" element={<PlayGoalsPage />} />
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </JobsProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
