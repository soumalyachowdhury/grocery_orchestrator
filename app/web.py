CHAT_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Grocery Chatbot</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Arial, sans-serif;
      --border: #d9e2dc;
      --brand: #1f7a4d;
      --brand-dark: #165a39;
      --bg: #f6f8f5;
      --user: #e7f1ff;
      --agent: #ffffff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: #17211b;
      display: grid;
      place-items: center;
      padding: 24px;
    }
    main {
      width: min(760px, 100%);
      height: min(760px, calc(100vh - 48px));
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 8px;
      display: grid;
      grid-template-rows: auto 1fr auto;
      overflow: hidden;
      box-shadow: 0 18px 50px rgba(31, 64, 47, 0.12);
    }
    header {
      padding: 18px 20px;
      border-bottom: 1px solid var(--border);
      background: #fbfdfb;
    }
    h1 {
      font-size: 20px;
      margin: 0 0 4px;
      letter-spacing: 0;
    }
    .status {
      margin: 0;
      color: #52655a;
      font-size: 14px;
    }
    #messages {
      padding: 20px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .message {
      max-width: 82%;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
      line-height: 1.45;
      white-space: pre-wrap;
    }
    .user {
      align-self: flex-end;
      background: var(--user);
      border-color: #c7dbf5;
    }
    .agent {
      align-self: flex-start;
      background: var(--agent);
    }
    details.debug {
      align-self: flex-start;
      width: min(100%, 620px);
      border: 1px dashed #aab7af;
      border-radius: 8px;
      padding: 10px 12px;
      background: #f8faf8;
      color: #34453b;
      font-size: 12px;
    }
    details.debug summary {
      cursor: pointer;
      font-weight: 700;
    }
    details.debug pre {
      margin: 10px 0 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .options {
      align-self: flex-start;
      width: min(100%, 620px);
      display: grid;
      gap: 8px;
    }
    .option-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }
    .option-row span {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .option-row button {
      min-height: 36px;
      padding: 0 12px;
    }
    form {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 10px;
      padding: 16px;
      border-top: 1px solid var(--border);
      background: #fbfdfb;
    }
    input {
      width: 100%;
      min-width: 0;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      font-size: 15px;
    }
    button {
      border: 0;
      border-radius: 6px;
      background: var(--brand);
      color: white;
      padding: 0 18px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }
    .secondary-button {
      border: 1px solid var(--border);
      background: #fff;
      color: #17211b;
    }
    .secondary-button.recording {
      border-color: #b42318;
      color: #b42318;
    }
    button:hover { background: var(--brand-dark); }
    button:disabled { opacity: 0.65; cursor: wait; }
    @media (max-width: 560px) {
      body { padding: 0; }
      main { height: 100vh; border-radius: 0; border: 0; }
      form { grid-template-columns: 1fr; }
      button { min-height: 44px; }
      .message { max-width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Grocery Chatbot</h1>
      <p class="status">Identify first with customer ID, loyalty ID, phone, or name. Then ask store questions or customer-detail questions.</p>
    </header>
    <section id="messages" aria-live="polite"></section>
    <form id="chat-form">
      <input id="message-input" name="message" autocomplete="off" placeholder="Start with: CUST10045, LOY10045, Soumalya, or 2016588874" required>
      <button id="record-button" class="secondary-button" type="button">Speak</button>
      <button id="send-button" type="submit">Send</button>
    </form>
  </main>
  <script>
    const form = document.querySelector("#chat-form");
    const input = document.querySelector("#message-input");
    const recordButton = document.querySelector("#record-button");
    const button = document.querySelector("#send-button");
    const messages = document.querySelector("#messages");
    let mediaRecorder = null;
    let audioChunks = [];
    const sessionIdKey = "grocery-chatbot-tab-session-id";
    let sessionId = window.sessionStorage.getItem(sessionIdKey);
    if (!sessionId) {
      sessionId = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : String(Date.now());
      window.sessionStorage.setItem(sessionIdKey, sessionId);
    }

    function addMessage(text, className) {
      const item = document.createElement("div");
      item.className = `message ${className}`;
      item.textContent = text;
      messages.appendChild(item);
      messages.scrollTop = messages.scrollHeight;
    }

    function addDebug(debug) {
      if (!debug) return;
      const item = document.createElement("details");
      item.className = "debug";
      item.open = true;
      const summary = document.createElement("summary");
      summary.textContent = "Debug info";
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(debug, null, 2);
      item.appendChild(summary);
      item.appendChild(pre);
      messages.appendChild(item);
      messages.scrollTop = messages.scrollHeight;
    }

    function addOptions(options) {
      if (!options || !options.length) return;
      const list = document.createElement("div");
      list.className = "options";

      options.forEach((option) => {
        const row = document.createElement("div");
        row.className = "option-row";
        const label = document.createElement("span");
        label.textContent = option.label;
        const actionButton = document.createElement("button");
        actionButton.type = "button";
        actionButton.textContent = "Select";
        actionButton.addEventListener("click", () => {
          sendMessage(option.action, option.label);
        });
        row.appendChild(label);
        row.appendChild(actionButton);
        list.appendChild(row);
      });

      messages.appendChild(list);
      messages.scrollTop = messages.scrollHeight;
    }

    async function sendMessage(message, displayText = message) {
      addMessage(displayText, "user");
      input.value = "";
      button.disabled = true;
      recordButton.disabled = true;

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, session_id: sessionId })
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const payload = await response.json();
        addMessage(payload.answer, "agent");
        addOptions(payload.options);
        addDebug(payload.debug);
      } catch (error) {
        addMessage("Sorry, the chatbot server could not process that message.", "agent");
      } finally {
        button.disabled = false;
        recordButton.disabled = false;
        input.focus();
      }
    }

    addMessage("Hi, I am ready to help with grocery questions and customer details.", "agent");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = input.value.trim();
      if (!message) return;
      await sendMessage(message);
    });

    async function sendAudioBlob(blob) {
      addMessage("Voice message recorded.", "user");
      button.disabled = true;
      recordButton.disabled = true;

      const formData = new FormData();
      formData.append("audio", blob, "browser-voice.webm");
      formData.append("session_id", sessionId);

      try {
        const response = await fetch("/api/voice-chat", {
          method: "POST",
          body: formData
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const payload = await response.json();
        if (payload.transcript) {
          addMessage(`Transcript: ${payload.transcript}`, "agent");
        }
        addMessage(payload.answer, "agent");
        addOptions(payload.options);
        addDebug(payload.debug);
      } catch (error) {
        addMessage("Sorry, the chatbot server could not process that audio message.", "agent");
      } finally {
        button.disabled = false;
        recordButton.disabled = false;
        input.focus();
      }
    }

    recordButton.addEventListener("click", async () => {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
        recordButton.textContent = "Speak";
        recordButton.classList.remove("recording");
        return;
      }

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        addMessage("This browser does not support microphone recording.", "agent");
        return;
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });

        mediaRecorder.addEventListener("dataavailable", (event) => {
          if (event.data.size > 0) {
            audioChunks.push(event.data);
          }
        });

        mediaRecorder.addEventListener("stop", async () => {
          stream.getTracks().forEach((track) => track.stop());
          const blob = new Blob(audioChunks, { type: "audio/webm" });
          await sendAudioBlob(blob);
        });

        mediaRecorder.start();
        recordButton.textContent = "Stop";
        recordButton.classList.add("recording");
      } catch (error) {
        addMessage("Microphone access was not available. Please allow microphone permission and try again.", "agent");
      }
    });
  </script>
</body>
</html>
"""
