/**
 * API client for the ViFA-Council backend.
 */

const API_BASE = 'http://localhost:8000';

export const api = {
  /**
   * List all conversations.
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`
    );
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Send a message and receive streaming updates.
   * @param {string} conversationId - The conversation ID
   * @param {object} payload - The message payload, including content and optional image
   * @param {function} onEvent - Callback function for each event: (eventType, data) => void
   * @returns {Promise<void>}
   */
  async sendMessageStream(conversationId, payload, onEvent) {
    const formData = new FormData();
    formData.append("content", payload.content || "");

    if (payload.image) {
      formData.append("image", payload.image.file);
    }

    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: "POST",
        body: formData,
      }
    );

    if (!response.ok) {
      throw new Error("Failed to send message");
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const result = await response.json();

      if (result.stage1_results) {
        onEvent("stage1_complete", result.stage1_results);
      }
      if (result.stage2_results) {
        onEvent("stage2_complete", result.stage2_results);
      }
      if (result.final_result) {
        onEvent("stage3_complete", {
          ...result.final_result,
          model:
            result.final_result.model ?? result.final_result.selected_model,
          response:
            result.final_result.response ??
            result.final_result.selected_response,
        });
      }

      onEvent("complete", result);
      return;
    }

    if (!response.body) {
      throw new Error("Streaming response body is unavailable");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const dispatchEvent = (eventBlock) => {
      const data = eventBlock
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).replace(/^ /, ""))
        .join("\n");

      if (!data) return;

      try {
        const event = JSON.parse(data);
        onEvent(event.type, event.data);
      } catch (error) {
        console.error("SSE parse error", error);
      }
    };

    const processBuffer = (flush = false) => {
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() || "";

      if (flush && buffer.trim()) {
        events.push(buffer);
        buffer = "";
      }

      events.forEach(dispatchEvent);
    };

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        buffer += decoder.decode();
        processBuffer(true);
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      processBuffer();
    }
  }
};
