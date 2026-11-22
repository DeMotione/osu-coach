import { useEffect, type RefObject } from "react";

/** Shows a <dialog> as a modal while ``open`` (and the component is there), and closes it otherwise. Where showModal
 * is missing (older WebViews, the tests' DOM), the ``open`` attribute stands in. */
export function useModal(ref: RefObject<HTMLDialogElement | null>, open = true) {
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    } else if (!open && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [ref, open]);
  useEffect(() => {
    const d = ref.current;
    return () => d?.close?.();
  }, [ref]);
}
