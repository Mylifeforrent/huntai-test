import { useSearchParams } from "react-router-dom";

export function useUrlState() {
  const [params, setParams] = useSearchParams();

  function get(key: string, fallback = ""): string {
    return params.get(key) ?? fallback;
  }

  function set(next: Record<string, string | undefined>) {
    const copy = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (!value) {
        copy.delete(key);
      } else {
        copy.set(key, value);
      }
    }
    setParams(copy, { replace: true });
  }

  return { params, get, set };
}
