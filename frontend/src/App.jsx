import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api } from './api';
import './App.css';

const normalizeFinalResult = (finalResult) => {
  if (!finalResult) return null;

  return {
    ...finalResult,
    model: finalResult.model ?? finalResult.selected_model ?? null,
    response: finalResult.response ?? finalResult.selected_response ?? null,
  };
};

const normalizeMessage = (message) => {
  if (message.role !== 'assistant') return message;

  const councilResponse = message.council_response || {};

  return {
    ...message,
    stage1: message.stage1 ?? councilResponse.stage1_results ?? null,
    stage2: message.stage2 ?? councilResponse.stage2_results ?? null,
    stage3: normalizeFinalResult(
      message.stage3 ?? councilResponse.final_result
    ),
  };
};

const normalizeConversation = (conversation) => ({
  ...conversation,
  messages: (conversation.messages || []).map(normalizeMessage),
});

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const updateLastAssistant = (updater) => {
    setCurrentConversation(prev => {
      if (!prev) return prev;

      const messages = [...prev.messages];
      const lastIndex = messages.length - 1;
      const last = messages[lastIndex];

      if (!last || last.role !== "assistant") return prev;

      messages[lastIndex] = updater({ ...last });
      return { ...prev, messages };
    });
  };

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  // Load conversations on mount
  useEffect(() => {
    let isActive = true;

    api.listConversations()
      .then((convs) => {
        if (isActive) setConversations(convs);
      })
      .catch((error) => {
        console.error('Failed to load conversations:', error);
      });

    return () => {
      isActive = false;
    };
  }, []);

  // Load conversation details when selected
  useEffect(() => {
    if (!currentConversationId) return undefined;

    let isActive = true;

    api.getConversation(currentConversationId)
      .then((conv) => {
        if (isActive) {
          setCurrentConversation(normalizeConversation(conv));
        }
      })
      .catch((error) => {
        console.error('Failed to load conversation:', error);
      });

    return () => {
      isActive = false;
    };
  }, [currentConversationId]);

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation();
      setConversations((previous) => [
        {
          id: newConv.id,
          created_at: newConv.created_at,
          title: newConv.title,
          message_count: 0,
        },
        ...previous,
      ]);
      setCurrentConversationId(newConv.id);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = (id) => {
    setCurrentConversationId(id);
  };

  const handleSendMessage = async ({ content, image = null }) => {
    if (!currentConversationId) return;

    setIsLoading(true);
    try {
      // Optimistically add user message to UI
      const userMessage = {
        role: 'user',
        content,
        image: image
          ? image.preview || URL.createObjectURL(image.file)
          : null,
      };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
      }));

      // Create a partial assistant message that will be updated progressively
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        loading: {
          stage1: false,
          stage2: false,
          stage3: false,
          synthesis: false,
        },
      };

      // Add the partial assistant message
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      // Send message with streaming
      await api.sendMessageStream(
        currentConversationId,
        { content, image },
        (type, payload) => {
          switch (type) {
            case "stage1_start":
              updateLastAssistant(msg => ({
                ...msg,
                loading: { ...msg.loading, stage1: true }
              }));
              break;

            case "stage1_complete":
              updateLastAssistant(msg => ({
                ...msg,
                stage1: payload,
                loading: { ...msg.loading, stage1: false }
              }));
              break;

            case "stage2_start":
              updateLastAssistant(msg => ({
                ...msg,
                loading: { ...msg.loading, stage2: true }
              }));
              break;

            case "stage2_complete":
              updateLastAssistant(msg => ({
                ...msg,
                stage2: payload,
                loading: { ...msg.loading, stage2: false }
              }));
              break;

            case "stage3_start":
              updateLastAssistant(msg => ({
                ...msg,
                loading: { ...msg.loading, stage3: true }
              }));
              break;

            case "stage3_complete":
              updateLastAssistant(msg => ({
                ...msg,
                stage3: payload,
                loading: { ...msg.loading, stage3: false }
              }));
              break;

            case "synthesis_start":
              updateLastAssistant(msg => ({
                ...msg,
                loading: { ...msg.loading, synthesis: true }
              }));
              break;

            case "image_generated":
              updateLastAssistant(msg => ({
                ...msg,
                stage3: {
                  ...msg.stage3,
                  generated_images: [
                    ...(msg.stage3?.generated_images || []),
                    payload,
                  ],
                },
              }));
              break;

            case "synthesis_error":
              updateLastAssistant(msg => ({
                ...msg,
                stage3: { ...msg.stage3, synthesis_error: payload?.message },
                loading: { ...msg.loading, synthesis: false },
              }));
              break;

            case "synthesis_complete":
              updateLastAssistant(msg => ({
                ...msg,
                stage3: {
                  ...msg.stage3,
                  generated_images: payload?.generated_images || [],
                  synthesis_error: payload?.synthesis_error || null,
                },
                loading: { ...msg.loading, synthesis: false },
              }));
              break;

            case "title_complete":
              loadConversations();
              break;

            case "complete":
              setIsLoading(false);
              loadConversations();
              break;

            case "error":
              console.error("Stream error:", payload);
              updateLastAssistant(msg => ({
                ...msg,
                stage3: {
                  model: "system",
                  response: payload?.message || "Council execution failed.",
                  evaluation: "The request did not complete.",
                  schema_valid: false,
                },
                loading: { stage1: false, stage2: false, stage3: false },
              }));
              setIsLoading(false);
              break;
          }
        }
      );
    } catch (error) {
      console.error('Failed to send message:', error);
      // Remove optimistic messages on error
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
      />
      <ChatInterface
        conversation={currentConversation}
        onSendMessage={handleSendMessage}
        isLoading={isLoading}
      />
    </div>
  );
}

export default App;
