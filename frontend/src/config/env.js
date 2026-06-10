export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "") || "";

export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || "";

export const SUPABASE_CONFIGURED = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

export const DEFAULT_CHAT_OPTIONS = {
  top_k: 10,
  rerank_top_k: 5,
};
