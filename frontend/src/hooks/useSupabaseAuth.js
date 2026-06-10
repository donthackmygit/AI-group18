import { useCallback, useEffect, useState } from "react";

import { requireSupabaseClient, supabase } from "../lib/supabaseClient.js";

export function useSupabaseAuth() {
  const [session, setSession] = useState(null);
  const [user, setUser] = useState(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  const ensureAnonymousSession = useCallback(async () => {
    const client = requireSupabaseClient();
    setIsAuthLoading(true);
    setAuthError(null);

    try {
      const { data: sessionData, error: sessionError } = await client.auth.getSession();
      if (sessionError) {
        throw sessionError;
      }

      if (sessionData.session) {
        setSession(sessionData.session);
        setUser(sessionData.session.user);
        return sessionData.session;
      }

      const { data, error } = await client.auth.signInAnonymously();
      if (error) {
        throw error;
      }

      setSession(data.session);
      setUser(data.user);
      return data.session;
    } catch (err) {
      setSession(null);
      setUser(null);
      setAuthError(
        err.message ||
          "Không đăng nhập được Supabase. Hãy kiểm tra env và bật Anonymous sign-ins.",
      );
      return null;
    } finally {
      setIsAuthLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    if (!supabase) {
      return;
    }
    await supabase.auth.signOut();
    setSession(null);
    setUser(null);
    await ensureAnonymousSession();
  }, [ensureAnonymousSession]);

  useEffect(() => {
    if (!supabase) {
      setAuthError("Thiếu cấu hình Supabase frontend.");
      setIsAuthLoading(false);
      return undefined;
    }

    let isMounted = true;
    ensureAnonymousSession();

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!isMounted) {
        return;
      }
      setSession(nextSession);
      setUser(nextSession?.user || null);
    });

    return () => {
      isMounted = false;
      data.subscription.unsubscribe();
    };
  }, [ensureAnonymousSession]);

  return {
    session,
    user,
    isAuthLoading,
    authError,
    signOut,
    refreshAuth: ensureAnonymousSession,
  };
}
