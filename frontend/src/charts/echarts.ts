/** ECharts with only the parts the app uses (keeps the bundle small). */
import { BarChart, HeatmapChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  PolarComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { LabelLayout } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  PolarComponent,
  VisualMapComponent,
  DataZoomComponent,
  TitleComponent,
  LabelLayout, // moves overlapping labels apart (the goal chart's)
  CanvasRenderer,
]);

export { echarts };
export type { EChartsCoreOption as Option } from "echarts/core";
