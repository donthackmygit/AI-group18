export function createId(prefix = "id") {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${prefix}_${crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function createConversation() {
  const now = new Date().toISOString();
  return {
    id: createId("conv"),
    title: "Cuộc trò chuyện mới",
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

export function titleFromQuestion(question) {
  const text = question.trim().replace(/\s+/g, " ");
  if (!text) {
    return "Cuộc trò chuyện mới";
  }
  return text.length > 54 ? `${text.slice(0, 51)}...` : text;
}
