function parseSseChunk(chunk) {
  const lines = String(chunk || "").replace(/\r\n/g, "\n").split("\n");
  let event = "message";
  const dataLines = [];
  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      event = line.slice(6).trim() || "message";
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0 && event === "message") return null;
  return { event, data: dataLines.join("\n") };
}

export function startAuthenticatedSse({
  url,
  token,
  onEvent,
  onOpen,
  onClose,
  onError,
  retryMs = 0,
  headers = {},
}) {
  const controller = new AbortController();
  let retryTimer = null;
  let closed = false;

  const clearRetry = () => {
    if (retryTimer) {
      clearTimeout(retryTimer);
      retryTimer = null;
    }
  };

  const scheduleRetry = () => {
    if (closed || controller.signal.aborted || Number(retryMs) <= 0) return;
    clearRetry();
    retryTimer = setTimeout(() => {
      retryTimer = null;
      void connect();
    }, Number(retryMs));
  };

  const connect = async () => {
    if (closed || controller.signal.aborted) return;
    let opened = false;
    try {
      const requestHeaders = {
        Accept: "text/event-stream",
        ...headers,
      };
      if (token) requestHeaders.Authorization = `Bearer ${token}`;
      const response = await fetch(url, {
        method: "GET",
        headers: requestHeaders,
        signal: controller.signal,
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`SSE request failed (${response.status})`);
      }
      if (!response.body) {
        throw new Error("SSE response body is empty");
      }
      opened = true;
      onOpen?.({ status: response.status, headers: response.headers });

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (!closed && !controller.signal.aborted) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let splitIndex = buffer.indexOf("\n\n");
        while (splitIndex >= 0) {
          const chunk = buffer.slice(0, splitIndex);
          buffer = buffer.slice(splitIndex + 2);
          const parsed = parseSseChunk(chunk);
          if (parsed) onEvent?.(parsed);
          splitIndex = buffer.indexOf("\n\n");
        }
      }

      if (opened) {
        onClose?.();
      }

      if (!closed && !controller.signal.aborted) {
        scheduleRetry();
      }
    } catch (error) {
      if (closed || controller.signal.aborted) return;
      if (opened) {
        onClose?.();
      }
      onError?.(error);
      scheduleRetry();
    }
  };

  void connect();

  return {
    close() {
      closed = true;
      clearRetry();
      controller.abort();
    },
  };
}
