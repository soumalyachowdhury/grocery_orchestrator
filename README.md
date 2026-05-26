# Grocery Orchestrator

Python chatbot orchestration service for a grocery store. It uses one chatbot agent that receives customer messages, answers common grocery questions, and calls the customer lookup API when the customer asks for account details.

## What It Does

- Presents a browser chatbot at `http://127.0.0.1:8000/`
- Receives chatbot messages through `POST /api/chat`
- Requires every chat session to identify a customer before regular conversation continues
- Remembers the identified customer separately for each `session_id`
- Browser tabs use separate per-tab session IDs, so two tabs act like two different users
- Stores the full customer API record in session memory, not only summary fields
- Detects whether the customer is asking for store help or personal customer details
- Calls the customer lookup API at:

```text
http://127.0.0.1:3000/api/customer-id?query=<phone-or-full-name>
```

- Returns a friendly response that can be shown directly in the chatbot
- Includes a mock customer lookup agent so the whole flow can be tested locally

## Project Layout

```text
app/
  main.py                  FastAPI server and chatbot page route
  config.py                Environment-based settings
  models.py                API request/response models
  web.py                   Browser chatbot HTML
  agents/
    chatbot_agent.py       Single chatbot agent that answers and calls customer API
customer_agent_server/
  main.py                  Mock customer lookup API on port 3000
node_server/
  twilio_whatsapp_server.js Twilio WhatsApp webhook bridge for Node.js
tests/
  test_orchestrator.py     Unit tests for routing behavior
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On Windows PowerShell, you can also run:

```powershell
.\scripts\setup.ps1
```

Copy the example config if you want to customize ports or API URLs:

```bash
copy .env.example .env
```

## Run Locally

Start the mock customer lookup agent:

```bash
uvicorn customer_agent_server.main:app --host 127.0.0.1 --port 3000 --reload
```

PowerShell helper:

```powershell
.\scripts\run-customer-agent.ps1
```

In another terminal, start the chatbot orchestrator:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

PowerShell helper:

```powershell
.\scripts\run-chatbot.ps1
```

Open the chatbot UI in your browser:

```text
http://127.0.0.1:8000/
```

## Example Requests

Identify the session first:

```bash
curl -X POST http://127.0.0.1:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"CUST10045\",\"session_id\":\"customer-chat-1\"}"
```

General grocery question:

```bash
curl -X POST http://127.0.0.1:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"What time is the grocery store open?\",\"session_id\":\"customer-chat-1\"}"
```

Customer-detail question by phone number:

```bash
curl -X POST http://127.0.0.1:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"Can you get my customer details for 2016588874?\"}"
```

Customer-detail question by full name:

```bash
curl -X POST http://127.0.0.1:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"Show customer details for Priya Sharma\"}"
```

Voice message from the browser:

Open `http://127.0.0.1:8000/`, click **Speak**, allow microphone permission, talk, then click **Stop**. The browser sends the recorded audio to `/api/voice-chat`. The chat shows both:

- the voice transcript
- the orchestrator's text response

Voice message upload API:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/voice-chat `
  -F "session_id=voice-session-1" `
  -F "audio=@C:\path\to\voice-message.webm;type=audio/webm"
```

The server transcribes the audio with `OPENAI_TRANSCRIPTION_MODEL`, passes the transcript to the same chatbot agent, and returns text:

```json
{
  "transcript": "get customer details for CUST10045",
  "answer": "I found customer ID CUST10045 ..."
}
```

Selectable item options:

After the session is identified, ask:

```text
show me items to buy and check prices
```

The API response can include:

```json
{
  "answer": "Please choose one of these options so I can take the next step.",
  "options": [
    {"label": "Check price: Milk", "value": "Milk", "action": "ACTION:CHECK_PRICE:Milk"},
    {"label": "Buy: Milk", "value": "Milk", "action": "ACTION:BUY_ITEM:Milk"}
  ]
}
```

The browser renders each option with a **Select** button. Other channels can send the `action` value back to `/api/chat` as the next `message`.

Twilio voice webhook:

```text
POST /webhooks/twilio/voice
```

This endpoint accepts Twilio form fields:

```text
From=+12015550123
SpeechResult=get customer details for CUST10045
```

It returns TwiML with both `<Message>` and `<Say>` using the chatbot's text response.

Twilio WhatsApp webhook through Node.js:

Start the customer lookup agent and Python chatbot orchestrator first. Then start the Node.js WhatsApp bridge:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-twilio-whatsapp.ps1
```

Or run Node directly:

```powershell
node .\node_server\twilio_whatsapp_server.js
```

Configure the Twilio WhatsApp sandbox or WhatsApp sender inbound webhook to:

```text
POST https://<your-public-url>/webhooks/twilio/whatsapp
```

For local testing, expose port `8080` with a tunnel such as ngrok and point Twilio to the public URL. The bridge reads Twilio's `From=whatsapp:+12016588874`, converts it to `2016588874`, and first sends that phone number to the orchestrator as the session identity. After the customer is identified, every WhatsApp message is forwarded to `/api/chat` with a stable session ID based on the WhatsApp sender.

If the orchestrator returns selectable options, the WhatsApp reply includes numbered choices. The customer can reply `1`, `2`, `3`, and the Node bridge sends the matching action back to the orchestrator.

Local webhook test:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8080/webhooks/twilio/whatsapp `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "From=whatsapp:%2B12016588874&Body=show%20me%20items%20to%20buy%20and%20check%20prices"
```

Configuration:

| Name | Default | Purpose |
| --- | --- | --- |
| `TWILIO_WHATSAPP_PORT` | `8080` | Local port for the Node.js WhatsApp bridge |
| `ORCHESTRATOR_API_URL` | `http://127.0.0.1:8000/api/chat` | Python orchestrator chat endpoint used by the bridge |
| `MAX_TWILIO_BODY_BYTES` | `1048576` | Maximum accepted Twilio webhook body size |

## Run Tests

```bash
pytest
```

PowerShell helper:

```powershell
.\scripts\test.ps1
```

## Push to GitHub from PowerShell

After installing Git for Windows, run:

```powershell
.\scripts\git-push.ps1
```

## Configuration

Environment variables:

| Name | Default | Purpose |
| --- | --- | --- |
| `CUSTOMER_LOOKUP_API_URL` | `http://127.0.0.1:3000/api/customer-id` | Customer lookup agent endpoint |
| `CUSTOMER_LOOKUP_TIMEOUT_SECONDS` | `5` | Timeout for customer lookup calls |
| `STORE_NAME` | `Fresh Basket Grocery` | Name used in chatbot replies |
| `OPENAI_API_KEY` | empty | Enables the OpenAI LLM orchestrator when set |
| `OPENAI_MODEL` | `gpt-5-mini` | OpenAI model used as the chatbot orchestrator |
| `OPENAI_TRANSCRIPTION_MODEL` | `gpt-4o-mini-transcribe` | OpenAI model used to transcribe uploaded voice messages |
| `USE_OPENAI_ORCHESTRATOR` | `true` | Uses OpenAI orchestration when an API key exists |

## Use GPT-5 Mini As Orchestrator

Create or edit `.env` in the project root:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-5-mini
USE_OPENAI_ORCHESTRATOR=true
```

Then restart the chatbot:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart-chatbot.ps1
```

When enabled, the chatbot sends each message to `gpt-5-mini`. The model can invoke the `lookup_customer` tool with structured arguments such as:

```json
{"query": "soumalya"}
```

The Python server then calls:

```text
http://127.0.0.1:3000/api/customer-id?query=soumalya
```

If `OPENAI_API_KEY` is not set or the OpenAI call fails, the chatbot falls back to the local parser so the app remains testable.

## Connector Docs

This repository also includes optional GitHub/Codex connector configuration notes under `config/`.
