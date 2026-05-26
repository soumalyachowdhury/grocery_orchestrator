const http = require("http");
const { URL } = require("url");

const PORT = Number(process.env.TWILIO_WHATSAPP_PORT || 8080);
const ORCHESTRATOR_API_URL =
  process.env.ORCHESTRATOR_API_URL || "http://127.0.0.1:8000/api/chat";
const MAX_BODY_BYTES = Number(process.env.MAX_TWILIO_BODY_BYTES || 1024 * 1024);

const identifiedSessions = new Set();
const optionMemory = new Map();

function normalizeWhatsAppAddress(value) {
  return String(value || "").trim();
}

function phoneQueryFromWhatsAppAddress(value) {
  const withoutPrefix = normalizeWhatsAppAddress(value).replace(/^whatsapp:/i, "");
  const digits = withoutPrefix.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) {
    return digits.slice(1);
  }
  return digits;
}

function sessionIdFromTwilio(from) {
  const address = normalizeWhatsAppAddress(from);
  return address || "twilio-whatsapp-unknown";
}

function escapeXml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function twiml(message) {
  return `<?xml version="1.0" encoding="UTF-8"?><Response><Message>${escapeXml(
    message,
  )}</Message></Response>`;
}

function jsonResponse(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function twimlResponse(res, statusCode, message) {
  const body = twiml(message);
  res.writeHead(statusCode, {
    "Content-Type": "application/xml",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;

    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("Twilio request body is too large."));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });

    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

async function callOrchestrator(message, sessionId) {
  const response = await fetch(ORCHESTRATOR_API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail ? JSON.stringify(payload.detail) : response.statusText;
    throw new Error(`Orchestrator returned HTTP ${response.status}: ${detail}`);
  }
  return payload;
}

function isIdentifiedResponse(payload) {
  return payload && ["customer_identified", "customer_lookup_cached", "customer_lookup"].includes(payload.intent);
}

function isStillAskingForIdentity(payload) {
  return (
    payload &&
    ["customer_identification_required", "customer_identification_failed"].includes(payload.intent)
  );
}

function looksLikeCustomerIdentifier(message) {
  const trimmed = String(message || "").trim();
  if (/^CUST\d+$/i.test(trimmed) || /^LOY\d+$/i.test(trimmed)) {
    return true;
  }

  if (trimmed.replace(/\D/g, "").length >= 7) {
    return true;
  }

  if (/^(my name is|name is|i am|i'm|this is)\s+[A-Za-z]/i.test(trimmed)) {
    return true;
  }

  return /^[A-Za-z][A-Za-z' -]{1,40}$/.test(trimmed) && trimmed.split(/\s+/).length <= 3;
}

function optionActionForMessage(sessionId, body) {
  const optionMap = optionMemory.get(sessionId);
  if (!optionMap) {
    return null;
  }

  const trimmed = String(body || "").trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }

  return optionMap.get(trimmed) || null;
}

function rememberOptions(sessionId, options) {
  if (!Array.isArray(options) || options.length === 0) {
    optionMemory.delete(sessionId);
    return;
  }

  const optionMap = new Map();
  options.forEach((option, index) => {
    if (option && option.action) {
      optionMap.set(String(index + 1), option.action);
    }
  });

  if (optionMap.size === 0) {
    optionMemory.delete(sessionId);
  } else {
    optionMemory.set(sessionId, optionMap);
  }
}

function formatWhatsAppAnswer(payload) {
  const parts = [payload.answer || "I could not produce a response."];
  if (Array.isArray(payload.options) && payload.options.length > 0) {
    const lines = payload.options.map((option, index) => `${index + 1}. ${option.label}`);
    parts.push(`Reply with a number:\n${lines.join("\n")}`);
  }
  return parts.join("\n\n");
}

async function handleWhatsAppWebhook(req, res) {
  let rawBody;
  try {
    rawBody = await readRequestBody(req);
  } catch (error) {
    twimlResponse(res, 413, error.message);
    return;
  }

  const form = new URLSearchParams(rawBody);
  const from = form.get("From") || "";
  const body = (form.get("Body") || "").trim();
  const sessionId = sessionIdFromTwilio(from);
  const senderPhoneQuery = phoneQueryFromWhatsAppAddress(from);

  if (!body) {
    twimlResponse(res, 200, "Please send your grocery question or customer lookup request.");
    return;
  }

  try {
    if (!identifiedSessions.has(sessionId) && senderPhoneQuery) {
      const identityResponse = await callOrchestrator(senderPhoneQuery, sessionId);
      if (isIdentifiedResponse(identityResponse)) {
        identifiedSessions.add(sessionId);
      } else if (isStillAskingForIdentity(identityResponse)) {
        if (!looksLikeCustomerIdentifier(body)) {
          rememberOptions(sessionId, identityResponse.options);
          twimlResponse(res, 200, formatWhatsAppAnswer(identityResponse));
          return;
        }
      }
    }

    const optionAction = optionActionForMessage(sessionId, body);
    const message = optionAction || body;
    const orchestratorResponse = await callOrchestrator(message, sessionId);
    if (isIdentifiedResponse(orchestratorResponse)) {
      identifiedSessions.add(sessionId);
    }
    rememberOptions(sessionId, orchestratorResponse.options);
    twimlResponse(res, 200, formatWhatsAppAnswer(orchestratorResponse));
  } catch (error) {
    console.error("Twilio WhatsApp webhook failed:", error);
    twimlResponse(
      res,
      200,
      "I could not reach the grocery orchestrator right now. Please try again in a moment.",
    );
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "127.0.0.1"}`);

  if (req.method === "GET" && url.pathname === "/health") {
    jsonResponse(res, 200, {
      status: "ok",
      orchestrator_api_url: ORCHESTRATOR_API_URL,
      identified_sessions: identifiedSessions.size,
    });
    return;
  }

  if (req.method === "POST" && url.pathname === "/webhooks/twilio/whatsapp") {
    await handleWhatsAppWebhook(req, res);
    return;
  }

  jsonResponse(res, 404, { error: "Not found" });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Twilio WhatsApp bridge listening on http://127.0.0.1:${PORT}`);
  console.log(`Forwarding messages to ${ORCHESTRATOR_API_URL}`);
});
