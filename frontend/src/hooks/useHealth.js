import { useCallback, useEffect, useState } from "react";

import { getHealth } from "../api/healthApi.js";

export function useHealth() {
  const [health, setHealth] = useState(null);
  const [isChecking, setIsChecking] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    const controller = new AbortController();
    setIsChecking(true);
    setError(null);

    try {
      const result = await getHealth({ signal: controller.signal });
      setHealth(result);
    } catch (err) {
      setHealth(null);
      setError(err.message || "Không kiểm tra được backend.");
    } finally {
      setIsChecking(false);
    }

    return () => controller.abort();
  }, []);

  useEffect(() => {
    let active = true;

    async function check() {
      if (!active) {
        return;
      }
      await refresh();
    }

    check();
    const timer = window.setInterval(check, 30000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  return {
    health,
    isChecking,
    error,
    refresh,
    isOnline: Boolean(health && !error),
  };
}
