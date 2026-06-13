import { useCallback, useEffect, useMemo, useState } from "react";

import { sendChatMessage } from "../api/chatApi.js";
import {
  createConversation as createStoredConversation,
  insertUserMessage,
  listConversations,
  listMessages,
  saveFeedback,
  updateConversationTitle,
} from "../api/conversationStore.js";
import { createId, titleFromQuestion } from "../utils/conversationId.js";
import { useSupabaseAuth } from "./useSupabaseAuth.js";

const DEFAULT_CONVERSATION_TITLE = "Cuộc trò chuyện mới";

export function useChat() {
  const auth = useSupabaseAuth();
  const [conversations, setConversations] = useState([]);
  const [messagesByConversation, setMessagesByConversation] = useState({});
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [chatError, setChatError] = useState(null);

  const refreshConversations = useCallback(async () => {
    if (!auth.user) {
      setConversations([]);
      setCurrentConversationId(null);
      return [];
    }

    setIsLoadingConversations(true);
    setChatError(null);
    try {
      const rows = await listConversations(auth.user.id);
      setConversations(rows);
      setCurrentConversationId((currentId) => {
        if (currentId && rows.some((conversation) => conversation.id === currentId)) {
          return currentId;
        }
        return rows[0]?.id || null;
      });
      return rows;
    } catch (err) {
      setChatError(err.message || "Không tải được danh sách hội thoại.");
      return [];
    } finally {
      setIsLoadingConversations(false);
    }
  }, [auth.user]);

  const refreshMessages = useCallback(async (conversationId) => {
    if (!conversationId) {
      return [];
    }

    setIsLoadingMessages(true);
    setChatError(null);
    try {
      const rows = await listMessages(conversationId);
      setMessagesByConversation((items) => ({
        ...items,
        [conversationId]: rows,
      }));
      return rows;
    } catch (err) {
      setChatError(err.message || "Không tải được tin nhắn.");
      return [];
    } finally {
      setIsLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    if (auth.isAuthLoading) {
      return;
    }
    refreshConversations();
  }, [auth.isAuthLoading, refreshConversations]);

  useEffect(() => {
    if (!currentConversationId) {
      return;
    }
    refreshMessages(currentConversationId);
  }, [currentConversationId, refreshMessages]);

  const currentConversation = useMemo(() => {
    const conversation = conversations.find((item) => item.id === currentConversationId);
    if (!conversation) {
      return null;
    }

    return {
      ...conversation,
      messages: messagesByConversation[conversation.id] || [],
    };
  }, [conversations, currentConversationId, messagesByConversation]);

  const setConversationMessages = useCallback((conversationId, updater) => {
    setMessagesByConversation((items) => {
      const currentMessages = items[conversationId] || [];
      return {
        ...items,
        [conversationId]: updater(currentMessages),
      };
    });
  }, []);

  const upsertConversation = useCallback((conversation) => {
    setConversations((items) => {
      const exists = items.some((item) => item.id === conversation.id);
      const nextItems = exists
        ? items.map((item) => (item.id === conversation.id ? { ...item, ...conversation } : item))
        : [conversation, ...items];

      return nextItems.sort(
        (a, b) => new Date(b.updatedAt || b.createdAt) - new Date(a.updatedAt || a.createdAt),
      );
    });
  }, []);

  const newConversation = useCallback(async () => {
    if (!auth.user) {
      setChatError("Chưa đăng nhập Supabase.");
      return;
    }

    setChatError(null);
    try {
      const conversation = await createStoredConversation(auth.user.id, DEFAULT_CONVERSATION_TITLE);
      upsertConversation(conversation);
      setCurrentConversationId(conversation.id);
      setMessagesByConversation((items) => ({
        ...items,
        [conversation.id]: [],
      }));
    } catch (err) {
      setChatError(err.message || "Không tạo được hội thoại mới.");
    }
  }, [auth.user, upsertConversation]);

  const selectConversation = useCallback((conversationId) => {
    setCurrentConversationId(conversationId);
  }, []);

  const ensureConversation = useCallback(
    async (question) => {
      if (!auth.user) {
        throw new Error("Chưa đăng nhập Supabase.");
      }

      const firstTitle = titleFromQuestion(question);
      if (!currentConversation) {
        const created = await createStoredConversation(auth.user.id, firstTitle);
        upsertConversation(created);
        setCurrentConversationId(created.id);
        setMessagesByConversation((items) => ({
          ...items,
          [created.id]: [],
        }));
        return created;
      }

      const currentMessages = messagesByConversation[currentConversation.id] || [];
      const shouldRetitle =
        currentMessages.length === 0 || currentConversation.title === DEFAULT_CONVERSATION_TITLE;
      const updated = await updateConversationTitle(
        currentConversation.id,
        shouldRetitle ? firstTitle : currentConversation.title,
      );
      upsertConversation(updated);
      return updated;
    },
    [auth.user, currentConversation, messagesByConversation, upsertConversation],
  );

  const sendMessage = useCallback(
    async (question, options = {}) => {
      const normalizedQuestion = question.trim();
      if (!normalizedQuestion || isSending) {
        return;
      }
      if (!auth.session?.access_token || !auth.user) {
        setChatError("Chưa có phiên đăng nhập Supabase.");
        return;
      }

      setIsSending(true);
      setChatError(null);

      let conversation = null;
      let pendingMessageId = null;

      try {
        conversation = await ensureConversation(normalizedQuestion);
        const userMessage = await insertUserMessage({
          conversationId: conversation.id,
          userId: auth.user.id,
          content: normalizedQuestion,
        });

        pendingMessageId = createId("pending");
        const pendingMessage = {
          id: pendingMessageId,
          role: "assistant",
          content: "Đang xử lý câu hỏi...",
          status: "loading",
          createdAt: new Date().toISOString(),
        };

        setConversationMessages(conversation.id, (messages) => [
          ...messages,
          userMessage,
          pendingMessage,
        ]);

        const response = await sendChatMessage(
          {
            ...options,
            question: normalizedQuestion,
            conversation_id: conversation.id,
          },
          { accessToken: auth.session.access_token },
        );

        const assistantMessage = {
          id: response.assistant_message_id || pendingMessageId,
          persistedId: response.assistant_message_id || null,
          role: "assistant",
          content: response.answer,
          status: "done",
          response,
          createdAt: new Date().toISOString(),
        };

        setConversationMessages(conversation.id, (messages) =>
          messages.map((message) =>
            message.id === pendingMessageId ? assistantMessage : message,
          ),
        );
        await refreshConversations();
      } catch (err) {
        const message =
          err.message || "Không gửi được câu hỏi. Hãy kiểm tra Supabase và FastAPI.";
        setChatError(message);

        if (conversation && pendingMessageId) {
          setConversationMessages(conversation.id, (messages) =>
            messages.map((item) =>
              item.id === pendingMessageId
                ? {
                    ...item,
                    content: message,
                    status: "error",
                    error: message,
                  }
                : item,
            ),
          );
        }
      } finally {
        setIsSending(false);
      }
    },
    [
      auth.session,
      auth.user,
      ensureConversation,
      isSending,
      refreshConversations,
      setConversationMessages,
    ],
  );

  const submitFeedback = useCallback(
    async (messageId, rating) => {
      if (!auth.user) {
        throw new Error("Chưa đăng nhập Supabase.");
      }
      if (!messageId) {
        throw new Error("Không có message_id để lưu feedback.");
      }
      await saveFeedback({ messageId, userId: auth.user.id, rating });
    },
    [auth.user],
  );

  return {
    conversations,
    currentConversation,
    currentConversationId,
    isSending,
    isLoadingConversations,
    isLoadingMessages,
    chatError,
    session: auth.session,
    user: auth.user,
    isAuthLoading: auth.isAuthLoading,
    authError: auth.authError,
    signOut: auth.signOut,
    newConversation,
    selectConversation,
    sendMessage,
    submitFeedback,
  };
}
