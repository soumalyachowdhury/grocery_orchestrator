from fastapi.testclient import TestClient

from app.main import app, get_chatbot_agent
from app.models import ChatResponse


class FakeVoiceAgent:
    async def respond_to_voice(self, audio_bytes: bytes, filename: str, content_type: str, session_id: str):
        return ChatResponse(
            answer="I found customer CUST10045.",
            intent="customer_lookup",
            delegated=True,
            data=None,
            debug={
                "voice_input": {
                    "filename": filename,
                    "content_type": content_type,
                    "transcript": "customer details for CUST10045",
                }
            },
            transcript="customer details for CUST10045",
        )

    async def respond(self, message: str, session_id: str = "default"):
        return ChatResponse(
            answer=f"Handled: {message}",
            intent="llm_response",
            delegated=False,
            data=None,
            debug={"session_id": session_id},
            transcript=None,
        )


def override_agent() -> FakeVoiceAgent:
    return FakeVoiceAgent()


def test_voice_chat_upload_returns_transcript_and_text_response() -> None:
    app.dependency_overrides[get_chatbot_agent] = override_agent
    client = TestClient(app)

    response = client.post(
        "/api/voice-chat",
        data={"session_id": "voice-test"},
        files={"audio": ("message.webm", b"fake audio", "audio/webm")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["transcript"] == "customer details for CUST10045"
    assert payload["answer"] == "I found customer CUST10045."


def test_twilio_voice_webhook_uses_speech_result() -> None:
    app.dependency_overrides[get_chatbot_agent] = override_agent
    client = TestClient(app)

    response = client.post(
        "/webhooks/twilio/voice",
        data={"From": "+12016588874", "SpeechResult": "customer details for CUST10045"},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<Message>Handled: customer details for CUST10045</Message>" in response.text
