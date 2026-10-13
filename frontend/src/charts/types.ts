/** The parts of ECharts' formatter / event parameters the app reads. */
export interface Param {
  dataIndex: number;
  seriesIndex?: number;
  seriesName?: string;
  name?: string;
  value?: unknown;
  data?: unknown;
  color?: string;
  axisValue?: string | number;
  axisValueLabel?: string;
  marker?: string;
}

export const params = (p: unknown): Param[] => (Array.isArray(p) ? (p as Param[]) : [p as Param]);
