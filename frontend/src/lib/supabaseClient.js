import { createClient } from "@supabase/supabase-js";

import { SUPABASE_ANON_KEY, SUPABASE_CONFIGURED, SUPABASE_URL } from "../config/env.js";

export const supabase = SUPABASE_CONFIGURED
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
      },
    })
  : null;

export function requireSupabaseClient() {
  if (!supabase) {
    throw new Error(
      "Thiếu VITE_SUPABASE_URL hoặc VITE_SUPABASE_ANON_KEY trong frontend/.env.",
    );
  }
  return supabase;
}
