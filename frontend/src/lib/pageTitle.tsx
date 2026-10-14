import { useMemo, useState, type ReactNode } from "react";

import { PageTitleContext } from "./pageTitleState";

export function PageTitleProvider({ children }: { children: ReactNode }) {
  const [visible, setVisible] = useState(true);
  const value = useMemo(() => ({ visible, setVisible }), [visible]);
  return <PageTitleContext.Provider value={value}>{children}</PageTitleContext.Provider>;
}
