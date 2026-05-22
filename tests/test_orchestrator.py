import httpx
import pytest
from httpx import Response

from app.agents.chatbot_agent import GroceryChatbotAgent


class FakeAsyncClient:
    requests: list[str] = []
    payload: dict[str, object] = {}
    payloads: list[dict[str, object]] = []

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    async def get(self, url: str) -> Response:
        self.requests.append(url)
        payload = self.payloads.pop(0) if self.payloads else self.payload
        return Response(200, json=payload, request=httpx.Request("GET", url))


class FakeOpenAIResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if "previous_response_id" not in kwargs:
            return {
                "id": "resp_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "lookup_customer",
                        "call_id": "call_1",
                        "arguments": "{\"query\":\"soumalya\"}",
                    }
                ],
            }
        return {
            "id": "resp_2",
            "output_text": "I found customer CUST10045 for Soumalya.",
            "output": [],
        }


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeOpenAIResponses()


def make_agent() -> GroceryChatbotAgent:
    return GroceryChatbotAgent(
        customer_api_url="http://127.0.0.1:3000/api/customer-id",
        store_name="Test Grocery",
    )


def make_openai_agent() -> GroceryChatbotAgent:
    agent = GroceryChatbotAgent(
        customer_api_url="http://127.0.0.1:3000/api/customer-id",
        store_name="Test Grocery",
        openai_api_key=None,
    )
    agent.openai_client = FakeOpenAIClient()
    agent.openai_model = "gpt-5-mini"
    return agent


def mock_customer_response(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.payload = payload
    FakeAsyncClient.payloads = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)


def mock_customer_responses(monkeypatch: pytest.MonkeyPatch, payloads: list[dict[str, object]]) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.payload = {}
    FakeAsyncClient.payloads = payloads.copy()
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)


@pytest.mark.asyncio
async def test_customer_lookup_delegates_by_phone(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "found": True,
            "query": "2016588874",
            "customer_id": "CUST-1001",
            "full_name": "Amit Kumar",
            "phone": "2016588874",
            "loyalty_points": 420,
            "preferred_store": "Fresh Basket Grocery - Jersey City",
        },
    )
    agent = make_agent()

    response = await agent.respond("Can you get my customer details for 2016588874?")

    assert response.intent == "customer_identified"
    assert response.delegated is True
    assert FakeAsyncClient.requests == ["http://127.0.0.1:3000/api/customer-id?query=2016588874"]
    assert "CUST-1001" in response.answer


@pytest.mark.asyncio
async def test_customer_lookup_delegates_by_full_name(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "found": True,
            "query": "Amit Kumar",
            "customer_id": "CUST-1001",
            "full_name": "Amit Kumar",
            "phone": "2016588874",
        },
    )
    agent = make_agent()

    response = await agent.respond("Show customer details for Amit Kumar")

    assert response.intent == "customer_identified"
    assert response.delegated is True
    assert FakeAsyncClient.requests == ["http://127.0.0.1:3000/api/customer-id?query=Amit+Kumar"]


@pytest.mark.asyncio
async def test_customer_lookup_delegates_by_partial_name(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "found": True,
            "query": "Amit",
            "customer_id": "CUST-1001",
            "full_name": "Amit Kumar",
            "phone": "2016588874",
        },
    )
    agent = make_agent()

    response = await agent.respond("Show customer details for Amit")

    assert response.intent == "customer_identified"
    assert response.delegated is True
    assert FakeAsyncClient.requests == ["http://127.0.0.1:3000/api/customer-id?query=Amit"]


@pytest.mark.asyncio
async def test_customer_lookup_asks_for_query_when_missing() -> None:
    agent = make_agent()

    response = await agent.respond("Can you show my details?")

    assert response.intent == "customer_identification_required"
    assert response.delegated is False


@pytest.mark.asyncio
async def test_customer_lookup_uses_followup_name_from_same_session(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "found": True,
            "query": "soumalya",
            "customer_id": "CUST-1003",
            "full_name": "Soumalya Chowdhury",
            "phone": "2016588874",
        },
    )
    agent = make_agent()

    first_response = await agent.respond("Can you show my details?", session_id="browser-session-1")
    second_response = await agent.respond("soumalya", session_id="browser-session-1")

    assert first_response.intent == "customer_identification_required"
    assert second_response.intent == "customer_identified"
    assert "Soumalya Chowdhury" in second_response.answer
    assert FakeAsyncClient.requests == ["http://127.0.0.1:3000/api/customer-id?query=soumalya"]
    assert second_response.debug is not None
    assert second_response.debug["agent_invoked"] == "GroceryChatbotAgent"
    assert second_response.debug["customer_api_invoked"] is True
    assert second_response.debug["customer_api_query"] == "soumalya"


@pytest.mark.asyncio
async def test_customer_lookup_reuses_cached_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "found": True,
            "query": "soumalya",
            "customer_id": "CUST-1003",
            "full_name": "Soumalya Chowdhury",
            "phone": "2016588874",
        },
    )
    agent = make_agent()

    first_response = await agent.respond("Show customer details for soumalya", session_id="browser-session-2")
    FakeAsyncClient.requests = []
    second_response = await agent.respond("Can you show my details?", session_id="browser-session-2")

    assert first_response.intent == "customer_identified"
    assert second_response.intent == "customer_record_answer"
    assert "Soumalya Chowdhury" in second_response.answer
    assert FakeAsyncClient.requests == []
    assert second_response.debug is not None
    assert second_response.debug["decision"] == "answered_from_full_customer_record"


@pytest.mark.asyncio
async def test_customer_lookup_supports_matches_api_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "message": "1 customer match found.",
            "query": "soumalya",
            "matches": [
                {
                    "customer_id": "CUST10045",
                    "loyalty_id": "LOY10045",
                    "coupon": {
                        "active": "Yes",
                        "offer": "15% on meat items",
                        "details": "15% off all meat items",
                    },
                    "meal_preference": "Non-Vegetarian",
                }
            ],
        },
    )
    agent = make_agent()

    first_response = await agent.respond("Can you show my details?", session_id="browser-session-3")
    second_response = await agent.respond("soumalya", session_id="browser-session-3")

    assert first_response.intent == "customer_identification_required"
    assert second_response.intent == "customer_identified"
    assert "CUST10045" in second_response.answer
    assert "LOY10045" in second_response.answer
    assert "15% on meat items" in second_response.answer


@pytest.mark.asyncio
async def test_customer_lookup_accepts_partial_phone_after_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "message": "1 customer match found.",
            "query": "201658874",
            "matches": [
                {
                    "customer_id": "CUST10045",
                    "loyalty_id": "LOY10045",
                    "meal_preference": "Non-Vegetarian",
                }
            ],
        },
    )
    agent = make_agent()

    first_response = await agent.respond("customer account details please?", session_id="browser-session-4")
    second_response = await agent.respond("201658874", session_id="browser-session-4")

    assert first_response.intent == "customer_identification_required"
    assert second_response.intent == "customer_identified"
    assert "CUST10045" in second_response.answer
    assert FakeAsyncClient.requests == ["http://127.0.0.1:3000/api/customer-id?query=201658874"]


@pytest.mark.asyncio
async def test_memory_question_reports_remembered_lookup_value() -> None:
    agent = make_agent()

    await agent.respond("my name is soumalya", session_id="browser-session-5")
    response = await agent.respond("tell me what I said my name is", session_id="browser-session-5")

    assert response.intent == "memory_recall"
    assert "soumalya" in response.answer.lower()


@pytest.mark.asyncio
async def test_customer_lookup_extracts_name_from_long_followup_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "message": "1 customer match found.",
            "query": "soumalya",
            "matches": [
                {
                    "customer_id": "CUST10045",
                    "loyalty_id": "LOY10045",
                }
            ],
        },
    )
    agent = make_agent()

    await agent.respond("get my customer details", session_id="browser-session-6")
    response = await agent.respond(
        "soumalya please remember this as I am customer and need to check few details of mine",
        session_id="browser-session-6",
    )

    assert response.intent == "customer_identified"
    assert FakeAsyncClient.requests == ["http://127.0.0.1:3000/api/customer-id?query=soumalya"]
    assert response.debug is not None
    assert response.debug["customer_api_query"] == "soumalya"


@pytest.mark.asyncio
async def test_openai_orchestrator_invokes_customer_lookup_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "message": "1 customer match found.",
            "query": "soumalya",
            "matches": [
                {
                    "customer_id": "CUST10045",
                    "loyalty_id": "LOY10045",
                }
            ],
        },
    )
    agent = make_openai_agent()
    agent.sessions["browser-session-openai"] = {
        "customer": {
            "customer_id": "CUST10045",
            "full_name": "Soumalya",
            "phone": "2016588874",
        },
        "identified_customer_id": "CUST10045",
        "identified_customer_query": "CUST10045",
    }

    response = await agent.respond(
        "soumalya please remember this as I am customer and need to check few details of mine",
        session_id="browser-session-openai",
    )

    assert response.intent == "customer_lookup"
    assert response.answer == "I found customer CUST10045 for Soumalya."
    assert FakeAsyncClient.requests == ["http://127.0.0.1:3000/api/customer-id?query=soumalya"]
    assert response.debug is not None
    assert response.debug["orchestrator_mode"] == "openai"
    assert response.debug["tool_call"] == {"name": "lookup_customer", "arguments": {"query": "soumalya"}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_query"),
    [
        ("get customer details for CUST10045", "CUST10045"),
        ("get loyalty details for LOY10045", "LOY10045"),
        ("get customer details for Soumalya", "Soumalya"),
        ("get customer details for 2016588874", "2016588874"),
    ],
)
async def test_customer_lookup_supported_query_patterns(
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    expected_query: str,
) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "message": "1 customer match found.",
            "query": expected_query,
            "matches": [
                {
                    "customer_id": "CUST10045",
                    "loyalty_id": "LOY10045",
                }
            ],
        },
    )
    agent = make_agent()

    response = await agent.respond(message)

    assert response.intent == "customer_identified"
    assert FakeAsyncClient.requests == [f"http://127.0.0.1:3000/api/customer-id?query={expected_query}"]
    assert response.debug is not None
    assert response.debug["customer_api_query"] == expected_query


@pytest.mark.asyncio
async def test_customer_lookup_supports_spreadsheet_style_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "message": "1 customer match found.",
            "query": "CUST10046",
            "matches": [
                {
                    "Customer ID": "CUST10046",
                    "Loyalty ID": "LOY10046",
                    "Customer Name": "Suman Kumar Chandra",
                    "Phone Number": "6363576032",
                    "Dietary Preference": "Non-Vegetarian",
                    "Active Coupon": "Yes",
                    "Coupon Details": "25% off all meat items",
                    "Coupon Valid From": "2026-06-01",
                    "Coupon Valid Until": "2026-12-31",
                    "Coupon": "15% on meat items",
                    "Preferred Channels": "WhatsApp, Mobile App, SMS",
                }
            ],
        },
    )
    agent = make_agent()

    response = await agent.respond("get customer details for CUST10046")

    assert response.intent == "customer_identified"
    assert "CUST10046" in response.answer
    assert "Suman Kumar Chandra" in response.answer
    assert "6363576032" in response.answer
    assert "LOY10046" in response.answer
    assert response.data is not None
    assert response.data["raw_record"]["Preferred Channels"] == "WhatsApp, Mobile App, SMS"


@pytest.mark.asyncio
async def test_sessions_keep_identified_customers_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_responses(
        monkeypatch,
        [
            {
                "message": "1 customer match found.",
                "query": "CUST10045",
                "matches": [
                    {
                        "Customer ID": "CUST10045",
                        "Customer Name": "Soumalya Chowdhury",
                        "Phone Number": "2016588874",
                        "Delivery Type": "Home Delivery",
                    }
                ],
            },
            {
                "message": "1 customer match found.",
                "query": "CUST10046",
                "matches": [
                    {
                        "Customer ID": "CUST10046",
                        "Customer Name": "Suman Kumar Chandra",
                        "Phone Number": "6363576032",
                        "Delivery Type": "Store Pickup",
                    }
                ],
            },
        ],
    )
    agent = make_agent()

    await agent.respond("CUST10045", session_id="tab-1")
    await agent.respond("CUST10046", session_id="tab-2")
    tab_1_response = await agent.respond("what is my delivery type?", session_id="tab-1")
    tab_2_response = await agent.respond("what is my delivery type?", session_id="tab-2")

    assert tab_1_response.answer == "Delivery Type: Home Delivery"
    assert tab_2_response.answer == "Delivery Type: Store Pickup"


@pytest.mark.asyncio
async def test_full_customer_record_fields_are_available_after_identification(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "message": "1 customer match found.",
            "query": "CUST10046",
            "matches": [
                {
                    "Customer ID": "CUST10046",
                    "Customer Name": "Suman Kumar Chandra",
                    "Preferred Channels": "WhatsApp, Mobile App, SMS",
                    "Frequently Purchased Categories": "Milk, Chicken, Eggs",
                    "Notes": "Interested in subscription reminders",
                }
            ],
        },
    )
    agent = make_agent()

    await agent.respond("CUST10046", session_id="tab-full-record")
    response = await agent.respond("what are my preferred channels?", session_id="tab-full-record")

    assert response.intent == "customer_record_answer"
    assert response.answer == "Preferred Channels: WhatsApp, Mobile App, SMS"


@pytest.mark.asyncio
async def test_item_action_options_use_customer_purchase_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_customer_response(
        monkeypatch,
        {
            "message": "1 customer match found.",
            "query": "CUST10046",
            "matches": [
                {
                    "Customer ID": "CUST10046",
                    "Customer Name": "Suman Kumar Chandra",
                    "Frequently Purchased Categories": "Milk, Chicken, Eggs",
                }
            ],
        },
    )
    agent = make_agent()

    await agent.respond("CUST10046", session_id="options-session")
    response = await agent.respond("show me items to buy and check prices", session_id="options-session")

    assert response.intent == "item_action_options"
    assert response.options is not None
    labels = [option.label for option in response.options]
    actions = [option.action for option in response.options]
    assert "Check price: Milk" in labels
    assert "Buy: Chicken" in labels
    assert "ACTION:CHECK_PRICE:Milk" in actions
    assert "ACTION:BUY_ITEM:Eggs" in actions


@pytest.mark.asyncio
async def test_item_option_selection_returns_follow_up_action() -> None:
    agent = make_agent()
    agent.sessions["selection-session"] = {
        "customer": {
            "customer_id": "CUST10046",
            "full_name": "Suman Kumar Chandra",
            "raw_record": {"Frequently Purchased Categories": "Milk, Chicken"},
        }
    }

    response = await agent.respond("ACTION:BUY_ITEM:Milk", session_id="selection-session")

    assert response.intent == "buy_item_selected"
    assert "Milk" in response.answer
    assert response.options is not None
    assert response.options[0].action == "ACTION:FULFILLMENT:pickup:Milk"


@pytest.mark.asyncio
async def test_general_grocery_question_stays_local() -> None:
    agent = make_agent()
    agent.sessions["default"] = {
        "customer": {
            "customer_id": "CUST10045",
            "full_name": "Soumalya",
            "phone": "2016588874",
        },
        "identified_customer_id": "CUST10045",
        "identified_customer_query": "CUST10045",
    }

    response = await agent.respond("What time do you open?")

    assert response.intent == "grocery_help"
    assert response.delegated is False
    assert "8:00 AM" in response.answer
