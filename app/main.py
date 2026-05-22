from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, Response

from app.agents.chatbot_agent import GroceryChatbotAgent
from app.config import Settings, get_settings
from app.models import ChatRequest, ChatResponse
from app.web import CHAT_PAGE_HTML

app = FastAPI(
    title="Grocery Chatbot",
    description="Single-agent chatbot API for grocery-store customer support.",
    version="1.0.0",
)


def get_chatbot_agent(settings: Settings = Depends(get_settings)) -> GroceryChatbotAgent:
    if not hasattr(app.state, "chatbot_agent"):
        app.state.chatbot_agent = GroceryChatbotAgent(
            customer_api_url=settings.customer_lookup_api_url,
            store_name=settings.store_name,
            timeout_seconds=settings.customer_lookup_timeout_seconds,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            openai_transcription_model=settings.openai_transcription_model,
            use_openai_orchestrator=settings.use_openai_orchestrator,
        )
    return app.state.chatbot_agent


@app.get("/", response_class=HTMLResponse)
async def chat_page() -> str:
    return CHAT_PAGE_HTML


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    chatbot_agent: GroceryChatbotAgent = Depends(get_chatbot_agent),
) -> ChatResponse:
    return await chatbot_agent.respond(request.message, session_id=request.session_id or "default")


@app.post("/api/voice-chat", response_model=ChatResponse)
async def voice_chat(
    audio: UploadFile = File(...),
    session_id: str = Form(default="default"),
    chatbot_agent: GroceryChatbotAgent = Depends(get_chatbot_agent),
) -> ChatResponse:
    audio_bytes = await audio.read()
    return await chatbot_agent.respond_to_voice(
        audio_bytes=audio_bytes,
        filename=audio.filename or "voice-message.webm",
        content_type=audio.content_type or "application/octet-stream",
        session_id=session_id,
    )


@app.post("/webhooks/twilio/voice")
async def twilio_voice_webhook(
    SpeechResult: str | None = Form(default=None),
    From: str | None = Form(default=None),
    chatbot_agent: GroceryChatbotAgent = Depends(get_chatbot_agent),
) -> Response:
    if not SpeechResult:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Gather input="speech" action="/webhooks/twilio/voice" method="POST" speechTimeout="auto">'
            '<Say>Please say your grocery question or customer lookup request.</Say>'
            '</Gather>'
            '<Say>I did not hear anything. Please call again.</Say>'
            '</Response>'
        )
        return Response(content=twiml, media_type="application/xml")

    session_id = From or "twilio-voice"
    agent_response = await chatbot_agent.respond(SpeechResult, session_id=session_id)
    safe_answer = (
        agent_response.answer.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{safe_answer}</Message>"
        f"<Say>{safe_answer}</Say>"
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")
