import { requireSupabaseClient } from "../lib/supabaseClient.js";

export async function listConversations(userId) {
  const client = requireSupabaseClient();
  const { data, error } = await client
    .from("conversations")
    .select("id,title,created_at,updated_at")
    .eq("user_id", userId)
    .order("updated_at", { ascending: false });

  if (error) {
    throw error;
  }

  return (data || []).map(mapConversationRow);
}

export async function createConversation(userId, title = "Cuoc tro chuyen moi") {
  const client = requireSupabaseClient();
  const { data, error } = await client
    .from("conversations")
    .insert({ user_id: userId, title })
    .select("id,title,created_at,updated_at")
    .single();

  if (error) {
    throw error;
  }

  return mapConversationRow(data);
}

export async function updateConversationTitle(conversationId, title) {
  const client = requireSupabaseClient();
  const { data, error } = await client
    .from("conversations")
    .update({ title })
    .eq("id", conversationId)
    .select("id,title,created_at,updated_at")
    .single();

  if (error) {
    throw error;
  }

  return mapConversationRow(data);
}

export async function listMessages(conversationId) {
  const client = requireSupabaseClient();
  const { data, error } = await client
    .from("messages")
    .select("id,conversation_id,user_id,role,content,citations,retrieval_metadata,created_at")
    .eq("conversation_id", conversationId)
    .order("created_at", { ascending: true });

  if (error) {
    throw error;
  }

  return (data || []).map(mapMessageRow);
}

export async function insertUserMessage({ conversationId, userId, content }) {
  const client = requireSupabaseClient();
  const { data, error } = await client
    .from("messages")
    .insert({
      conversation_id: conversationId,
      user_id: userId,
      role: "user",
      content,
    })
    .select("id,conversation_id,user_id,role,content,citations,retrieval_metadata,created_at")
    .single();

  if (error) {
    throw error;
  }

  return mapMessageRow(data);
}

export async function saveFeedback({ messageId, userId, rating, comment = null }) {
  const client = requireSupabaseClient();
  const { error } = await client.from("feedback").upsert(
    {
      message_id: messageId,
      user_id: userId,
      rating,
      comment,
    },
    { onConflict: "message_id,user_id" },
  );

  if (error) {
    throw error;
  }
}

export function mapConversationRow(row) {
  return {
    id: row.id,
    title: row.title,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    messages: [],
  };
}

export function mapMessageRow(row) {
  const base = {
    id: row.id,
    persistedId: row.id,
    role: row.role,
    content: row.content,
    createdAt: row.created_at,
    status: "done",
  };

  if (row.role === "assistant") {
    return {
      ...base,
      response: buildAssistantResponse(row),
    };
  }

  return base;
}

function buildAssistantResponse(row) {
  const metadata = row.retrieval_metadata || {};
  return {
    answer: row.content,
    conversation_id: row.conversation_id,
    assistant_message_id: row.id,
    mode: metadata.mode || "llm",
    citations: row.citations || [],
    confidence: metadata.confidence ?? null,
    warning: metadata.warning || null,
    calculation: metadata.calculation || null,
    classification: metadata.classification || null,
    routing: metadata.routing || null,
    query_embedding: metadata.query_embedding || null,
    retrieval: metadata.retrieval || null,
    reranking: metadata.reranking || null,
    tax_calculation: metadata.tax_calculation || null,
    response_validation: metadata.response_validation || null,
    response_formatter: metadata.response_formatter || null,
  };
}
