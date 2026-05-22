import json
import re
from urllib.parse import urlencode

import httpx
try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - only used when dependency is missing locally.
    AsyncOpenAI = None  # type: ignore[assignment]

from app.models import ChatResponse, CustomerLookupResult


CUSTOMER_DETAIL_KEYWORDS = (
    "my details",
    "customer details",
    "account details",
    "loyalty details",
    "loyalty points",
    "customer id",
    "customer profile",
    "my profile",
)

QUERY_STOP_WORDS = {
    "a",
    "am",
    "an",
    "and",
    "as",
    "before",
    "check",
    "close",
    "customer",
    "details",
    "few",
    "for",
    "i",
    "is",
    "lookup",
    "me",
    "mine",
    "my",
    "name",
    "need",
    "of",
    "open",
    "please",
    "remember",
    "said",
    "the",
    "this",
    "time",
    "to",
    "want",
    "what",
    "when",
    "where",
    "you",
}

CUSTOMER_ID_PATTERN = r"\bCUST\d+\b"
LOYALTY_ID_PATTERN = r"\bLOY\d+\b"
PHONE_PATTERN = r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
PARTIAL_PHONE_PATTERN = r"\b[+\d][\d().\-\s]{6,}\b"


class GroceryChatbotAgent:
    """Single chatbot agent that answers messages and calls the customer API when needed."""

    def __init__(
        self,
        customer_api_url: str,
        store_name: str,
        timeout_seconds: float = 5.0,
        openai_api_key: str | None = None,
        openai_model: str = "gpt-5-mini",
        openai_transcription_model: str = "gpt-4o-mini-transcribe",
        use_openai_orchestrator: bool = True,
    ) -> None:
        self.customer_api_url = customer_api_url
        self.store_name = store_name
        self.timeout_seconds = timeout_seconds
        self.openai_model = openai_model
        self.openai_transcription_model = openai_transcription_model
        self.use_openai_orchestrator = use_openai_orchestrator
        self.openai_api_key = openai_api_key
        self.openai_client = (
            AsyncOpenAI(api_key=openai_api_key)
            if AsyncOpenAI is not None and openai_api_key and use_openai_orchestrator
            else None
        )
        self.audio_client = AsyncOpenAI(api_key=openai_api_key) if AsyncOpenAI is not None and openai_api_key else None
        self.sessions: dict[str, dict[str, object]] = {}

    async def respond(self, message: str, session_id: str = "default") -> ChatResponse:
        clean_message = message.strip()
        session = self.sessions.setdefault(session_id, {})
        debug: dict[str, object] = {
            "agent_invoked": "GroceryChatbotAgent",
            "session_id": session_id,
            "incoming_message": clean_message,
            "customer_api_invoked": False,
            "customer_api_url": None,
            "customer_api_query": None,
            "session_before": self._debug_session(session),
        }
        identification_response = await self._require_customer_identification(clean_message, session, debug)
        if identification_response is not None:
            return identification_response

        option_response = self._respond_with_action_options(clean_message, session, debug)
        if option_response is not None:
            return option_response

        if self.openai_client is not None:
            debug["orchestrator_mode"] = "openai"
            debug["openai_model"] = self.openai_model
            try:
                return await self._respond_with_openai(clean_message, session_id, session, debug)
            except Exception as exc:  # Keep the local chatbot usable if the LLM call fails.
                debug["openai_error"] = str(exc)
                debug["orchestrator_mode"] = "local_fallback_after_openai_error"
        else:
            debug["orchestrator_mode"] = "local_fallback"

        return await self._respond_locally(clean_message, session, debug)

    def _respond_with_action_options(
        self,
        clean_message: str,
        session: dict[str, object],
        debug: dict[str, object],
    ) -> ChatResponse | None:
        normalized = clean_message.lower()
        customer = session.get("customer") if isinstance(session.get("customer"), dict) else {}
        raw_record = customer.get("raw_record") if isinstance(customer, dict) else {}
        raw_record = raw_record if isinstance(raw_record, dict) else {}
        frequent_categories = str(raw_record.get("Frequently Purchased Categories", "")).strip()

        if clean_message.startswith("ACTION:CHECK_PRICE:"):
            item = clean_message.split(":", 2)[2].strip()
            debug["decision"] = "selected_check_price_option"
            return ChatResponse(
                answer=f"I will check the current price for {item}.",
                intent="check_price_selected",
                delegated=False,
                data={"selected_item": item, "action": "check_price"},
                debug=self._finish_debug(debug, session),
            )

        if clean_message.startswith("ACTION:BUY_ITEM:"):
            item = clean_message.split(":", 2)[2].strip()
            debug["decision"] = "selected_buy_item_option"
            return ChatResponse(
                answer=f"I selected {item} for purchase. The next step is to confirm quantity and fulfillment method.",
                intent="buy_item_selected",
                delegated=False,
                data={"selected_item": item, "action": "buy_item"},
                options=[
                    {"label": "Store pickup", "value": item, "action": f"ACTION:FULFILLMENT:pickup:{item}"},
                    {"label": "Home delivery", "value": item, "action": f"ACTION:FULFILLMENT:delivery:{item}"},
                ],
                debug=self._finish_debug(debug, session),
            )

        if clean_message.startswith("ACTION:FULFILLMENT:"):
            _, _, fulfillment, item = clean_message.split(":", 3)
            debug["decision"] = "selected_fulfillment_option"
            return ChatResponse(
                answer=f"Got it. I will use {fulfillment.replace('-', ' ')} for {item}.",
                intent="fulfillment_selected",
                delegated=False,
                data={"selected_item": item, "fulfillment": fulfillment},
                debug=self._finish_debug(debug, session),
            )

        asks_shopping_options = any(
            phrase in normalized
            for phrase in [
                "buy",
                "purchase",
                "shop",
                "items to buy",
                "check price",
                "check prices",
                "prices",
            ]
        )
        if not asks_shopping_options:
            return None

        items = self._suggest_items_from_record(frequent_categories)
        debug["decision"] = "presented_item_action_options"
        return ChatResponse(
            answer="Please choose one of these options so I can take the next step.",
            intent="item_action_options",
            delegated=False,
            data={"source": "customer_record", "frequently_purchased_categories": frequent_categories},
            options=[
                {"label": f"Check price: {item}", "value": item, "action": f"ACTION:CHECK_PRICE:{item}"}
                for item in items
            ]
            + [
                {"label": f"Buy: {item}", "value": item, "action": f"ACTION:BUY_ITEM:{item}"}
                for item in items
            ],
            debug=self._finish_debug(debug, session),
        )

    def _suggest_items_from_record(self, frequent_categories: str) -> list[str]:
        if frequent_categories:
            items = [item.strip() for item in frequent_categories.split(",") if item.strip()]
            if items:
                return items[:5]

        return ["Milk", "Eggs", "Bread", "Chicken", "Bananas"]

    async def _require_customer_identification(
        self,
        clean_message: str,
        session: dict[str, object],
        debug: dict[str, object],
    ) -> ChatResponse | None:
        if session.get("customer"):
            return None

        query = (
            self._extract_standalone_customer_query(clean_message) or self._extract_customer_query(clean_message)
            if session.get("awaiting_customer_query")
            else self._extract_identification_query(clean_message)
        )
        if not query:
            session["awaiting_customer_query"] = True
            debug["orchestrator_mode"] = "identification_gate"
            debug["decision"] = "blocked_until_customer_identifies"
            return ChatResponse(
                answer=(
                    "Before we continue, please identify yourself with your customer ID, loyalty ID, "
                    "phone number, or name. For example: CUST10045, LOY10045, Soumalya, or 2016588874."
                ),
                intent="customer_identification_required",
                delegated=False,
                debug=self._finish_debug(debug, session),
            )

        session["awaiting_customer_query"] = False
        session["last_customer_query"] = query
        debug["orchestrator_mode"] = "identification_gate"
        result = await self._lookup_customer(query, debug)
        if not result.found:
            session["awaiting_customer_query"] = True
            debug["decision"] = "customer_identification_failed"
            return ChatResponse(
                answer=(
                    result.message
                    or "I could not identify that customer. Please enter a valid customer ID, loyalty ID, phone number, or name."
                ),
                intent="customer_identification_failed",
                delegated=True,
                data=result.model_dump(),
                debug=self._finish_debug(debug, session),
            )

        session["customer"] = result.model_dump()
        session["identified_customer_id"] = result.customer_id
        session["identified_customer_query"] = query
        debug["decision"] = "customer_identified"
        return self._customer_response_from_data(
            result.model_dump(),
            intent="customer_identified",
            delegated=True,
            data=result.model_dump(),
            debug=self._finish_debug(debug, session),
            prefix="Thanks, I identified this chat session. ",
        )

    async def respond_to_voice(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        session_id: str = "default",
    ) -> ChatResponse:
        transcript = await self.transcribe_audio(audio_bytes, filename, content_type)
        response = await self.respond(transcript, session_id=session_id)
        response.transcript = transcript
        if response.debug is None:
            response.debug = {}
        response.debug["voice_input"] = {
            "filename": filename,
            "content_type": content_type,
            "transcription_model": self.openai_transcription_model,
            "transcript": transcript,
        }
        return response

    async def transcribe_audio(self, audio_bytes: bytes, filename: str, content_type: str) -> str:
        if self.audio_client is None:
            raise RuntimeError("OPENAI_API_KEY is required to transcribe voice messages.")

        transcription = await self.audio_client.audio.transcriptions.create(
            model=self.openai_transcription_model,
            file=(filename, audio_bytes, content_type),
        )
        text = self._get_attr(transcription, "text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Voice transcription returned no text.")
        return text.strip()

    async def _respond_locally(
        self,
        clean_message: str,
        session: dict[str, object],
        debug: dict[str, object],
    ) -> ChatResponse:
        identity_query = self._extract_customer_query(clean_message)
        if identity_query:
            session["last_customer_query"] = identity_query

        remembered_answer = self._answer_remembered_identity_question(clean_message, session)
        if remembered_answer:
            debug["decision"] = "answered_from_memory"
            return ChatResponse(
                answer=remembered_answer,
                intent="memory_recall",
                delegated=False,
                debug=self._finish_debug(debug, session),
            )

        raw_record_answer = self._answer_from_raw_customer_record(clean_message, session)
        if raw_record_answer:
            debug["decision"] = "answered_from_full_customer_record"
            return ChatResponse(
                answer=raw_record_answer,
                intent="customer_record_answer",
                delegated=False,
                data=session.get("customer") if isinstance(session.get("customer"), dict) else None,
                debug=self._finish_debug(debug, session),
            )

        if self._is_customer_detail_question(clean_message) or session.get("awaiting_customer_query"):
            if session.get("awaiting_customer_query"):
                query = self._extract_standalone_customer_query(clean_message) or identity_query
            else:
                query = identity_query

            if not query and session.get("customer"):
                debug["decision"] = "returned_cached_customer"
                return self._customer_response_from_data(
                    session["customer"],
                    intent="customer_lookup_cached",
                    delegated=False,
                    debug=self._finish_debug(debug, session),
                )

            if not query and session.get("last_customer_query"):
                query = str(session["last_customer_query"])

            if not query:
                session["awaiting_customer_query"] = True
                debug["decision"] = "asked_for_customer_query"
                return ChatResponse(
                    answer="Please enter your phone number or part of your name so I can look up your customer details.",
                    intent="customer_lookup_missing_query",
                    delegated=True,
                    debug=self._finish_debug(debug, session),
                )

            session["awaiting_customer_query"] = False
            session["last_customer_query"] = query
            result = await self._lookup_customer(query, debug)
            if not result.found:
                session["awaiting_customer_query"] = True
                debug["decision"] = "customer_not_found_asked_for_another_query"
                return ChatResponse(
                    answer=(
                        result.message
                        or "I could not find a customer profile for that phone number or name. Please enter another phone number or name."
                    ),
                    intent="customer_lookup",
                    delegated=True,
                    data=result.model_dump(),
                    debug=self._finish_debug(debug, session),
                )

            session["customer"] = result.model_dump()
            debug["decision"] = "customer_found_from_api"
            return self._customer_response_from_data(
                result.model_dump(),
                intent="customer_lookup",
                delegated=True,
                data=result.model_dump(),
                debug=self._finish_debug(debug, session),
            )

        if identity_query:
            debug["decision"] = "remembered_customer_query"
            return ChatResponse(
                answer=(
                    f"I will remember '{identity_query}' for this chat. "
                    "Ask me for your customer details when you want me to look it up."
                ),
                intent="remember_customer_query",
                delegated=False,
                debug=self._finish_debug(debug, session),
            )

        debug["decision"] = "answered_grocery_question"
        return ChatResponse(
            answer=self._answer_grocery_question(clean_message),
            intent="grocery_help",
            delegated=False,
            debug=self._finish_debug(debug, session),
        )

    async def _respond_with_openai(
        self,
        clean_message: str,
        session_id: str,
        session: dict[str, object],
        debug: dict[str, object],
    ) -> ChatResponse:
        messages = self._session_messages(session)
        messages.append({"role": "user", "content": clean_message})
        system_prompt = self._build_orchestrator_prompt(session)
        tools = [self._lookup_customer_tool_schema()]

        response = await self.openai_client.responses.create(
            model=self.openai_model,
            input=[
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            tools=tools,
        )
        debug["openai_response_id"] = self._get_attr(response, "id")
        tool_call = self._find_tool_call(response)

        if tool_call is None:
            answer = self._response_text(response) or self._answer_grocery_question(clean_message)
            self._append_session_message(session, "user", clean_message)
            self._append_session_message(session, "assistant", answer)
            debug["decision"] = "openai_answered_without_tool"
            return ChatResponse(
                answer=answer,
                intent="llm_response",
                delegated=False,
                debug=self._finish_debug(debug, session),
            )

        arguments = self._tool_call_arguments(tool_call)
        query = str(arguments.get("query", "")).strip()
        debug["tool_call"] = {
            "name": self._get_attr(tool_call, "name"),
            "arguments": arguments,
        }
        if not query:
            session["awaiting_customer_query"] = True
            answer = "Please enter your phone number or part of your name so I can look up your customer details."
            self._append_session_message(session, "user", clean_message)
            self._append_session_message(session, "assistant", answer)
            debug["decision"] = "openai_requested_lookup_without_query"
            return ChatResponse(
                answer=answer,
                intent="customer_lookup_missing_query",
                delegated=True,
                debug=self._finish_debug(debug, session),
            )

        session["awaiting_customer_query"] = False
        session["last_customer_query"] = query
        result = await self._lookup_customer(query, debug)
        if result.found:
            session["customer"] = result.model_dump()

        tool_output = result.model_dump()
        followup_response = await self.openai_client.responses.create(
            model=self.openai_model,
            previous_response_id=self._get_attr(response, "id"),
            input=[
                {
                    "type": "function_call_output",
                    "call_id": self._get_attr(tool_call, "call_id"),
                    "output": json.dumps(tool_output),
                }
            ],
        )
        answer = self._response_text(followup_response)
        if not answer:
            answer = (
                self._customer_response_from_data(
                    result.model_dump(),
                    intent="customer_lookup",
                    delegated=True,
                    debug=self._finish_debug(debug, session),
                    data=result.model_dump(),
                ).answer
                if result.found
                else result.message or "No customer found for that search."
            )

        self._append_session_message(session, "user", clean_message)
        self._append_session_message(session, "assistant", answer)
        debug["openai_followup_response_id"] = self._get_attr(followup_response, "id")
        debug["decision"] = "openai_invoked_lookup_customer"
        return ChatResponse(
            answer=answer,
            intent="customer_lookup",
            delegated=True,
            data=result.model_dump(),
            debug=self._finish_debug(debug, session),
        )

    def _build_orchestrator_prompt(self, session: dict[str, object]) -> str:
        memory = self._debug_session(session)
        return (
            f"You are the single AI chatbot agent for {self.store_name}. "
            "Answer grocery store questions naturally and briefly. "
            "A customer must already be identified before this prompt is used. "
            "Use the current session memory and full stored customer record to answer questions about the customer "
            "without calling tools again when the information is already present. "
            "When the customer asks for account, loyalty, coupon, preference, profile, or customer details, "
            "call the lookup_customer tool with exactly one lookup value. Supported lookup values are customer IDs "
            "like CUST10045, loyalty IDs like LOY10045, phone numbers like 2016588874, or names/partial names like Soumalya. "
            "Extract only the lookup value, not the whole sentence. "
            "If the user previously supplied a name or phone in this conversation, use it when they ask for details. "
            "If you do not have enough information, ask for a phone number or part of their name. "
            f"Current session memory: {json.dumps(memory)}. "
            f"Full stored customer record: {json.dumps(self._raw_record_for_prompt(session))}"
        )

    def _lookup_customer_tool_schema(self) -> dict[str, object]:
        return {
            "type": "function",
            "name": "lookup_customer",
            "description": "Look up a grocery customer by customer ID, loyalty ID, phone number, full name, or partial name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Only one lookup value, such as CUST10045, LOY10045, Soumalya, or 2016588874.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        }

    def _session_messages(self, session: dict[str, object]) -> list[dict[str, str]]:
        messages = session.get("messages")
        if isinstance(messages, list):
            return [message for message in messages if isinstance(message, dict)][-10:]
        return []

    def _append_session_message(self, session: dict[str, object], role: str, content: str) -> None:
        messages = session.setdefault("messages", [])
        if isinstance(messages, list):
            messages.append({"role": role, "content": content})
            del messages[:-10]

    def _find_tool_call(self, response: object) -> object | None:
        output = self._get_attr(response, "output", [])
        if not isinstance(output, list):
            return None

        for item in output:
            if self._get_attr(item, "type") == "function_call" and self._get_attr(item, "name") == "lookup_customer":
                return item
        return None

    def _tool_call_arguments(self, tool_call: object) -> dict[str, object]:
        raw_arguments = self._get_attr(tool_call, "arguments", "{}")
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str):
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _response_text(self, response: object) -> str | None:
        output_text = self._get_attr(response, "output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output = self._get_attr(response, "output", [])
        if not isinstance(output, list):
            return None

        text_parts: list[str] = []
        for item in output:
            content = self._get_attr(item, "content", [])
            if not isinstance(content, list):
                continue
            for content_item in content:
                text = self._get_attr(content_item, "text")
                if isinstance(text, str):
                    text_parts.append(text)
        text = " ".join(text_parts).strip()
        return text or None

    def _get_attr(self, value: object, key: str, default: object | None = None) -> object:
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _is_customer_detail_question(self, message: str) -> bool:
        normalized = message.lower()
        return any(keyword in normalized for keyword in CUSTOMER_DETAIL_KEYWORDS)

    def _extract_customer_query(self, message: str) -> str | None:
        customer_id_match = re.search(CUSTOMER_ID_PATTERN, message, flags=re.IGNORECASE)
        if customer_id_match:
            return customer_id_match.group(0).upper()

        loyalty_id_match = re.search(LOYALTY_ID_PATTERN, message, flags=re.IGNORECASE)
        if loyalty_id_match:
            return loyalty_id_match.group(0).upper()

        phone_match = re.search(PHONE_PATTERN, message)
        if phone_match:
            return re.sub(r"\D", "", phone_match.group(0))

        digit_match = re.search(PARTIAL_PHONE_PATTERN, message)
        if digit_match:
            return re.sub(r"\D", "", digit_match.group(0))

        name_patterns = (
            r"(?:my name is|name is|i am|i'm|this is)\s+([A-Za-z][A-Za-z' -]{1,}?)(?:\s+(?:please|and|as|to|for|because|,|\.|\?|$).*)?$",
            r"(?:for|of)\s+([A-Za-z][A-Za-z' -]{1,}?)(?:\s+(?:please|and|as|to|because|,|\.|\?|$).*)?$",
            r"(?:phone is|phone number is|number is|mobile is)\s+([+\d][\d().\-\s]{6,})$",
            r"customer details\s+([A-Za-z][A-Za-z' -]{1,}?)(?:\s+(?:please|and|as|to|for|because|,|\.|\?|$).*)?$",
            r"details\s+([A-Za-z][A-Za-z' -]{1,}?)(?:\s+(?:please|and|as|to|for|because|,|\.|\?|$).*)?$",
        )
        for pattern in name_patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                candidate = self._clean_name_candidate(match.group(1))
                if candidate:
                    if re.search(r"\d", candidate):
                        return re.sub(r"\D", "", candidate)
                    return candidate

        return None

    def _extract_standalone_customer_query(self, message: str) -> str | None:
        customer_id_match = re.search(CUSTOMER_ID_PATTERN, message, flags=re.IGNORECASE)
        if customer_id_match:
            return customer_id_match.group(0).upper()

        loyalty_id_match = re.search(LOYALTY_ID_PATTERN, message, flags=re.IGNORECASE)
        if loyalty_id_match:
            return loyalty_id_match.group(0).upper()

        phone_match = re.search(PHONE_PATTERN, message)
        if phone_match:
            return re.sub(r"\D", "", phone_match.group(0))

        digit_match = re.fullmatch(r"[+\d][\d().\-\s]{6,}", message.strip())
        if digit_match:
            return re.sub(r"\D", "", digit_match.group(0))

        candidate = re.sub(r"\s+", " ", message).strip(" .?")
        if re.search(r"[A-Za-z]", candidate):
            return self._extract_likely_name_token(candidate)

        return None

    def _extract_identification_query(self, message: str) -> str | None:
        query = self._extract_customer_query(message)
        if query:
            return query

        normalized = re.sub(r"\s+", " ", message).strip(" .?")
        word_count = len(re.findall(r"[A-Za-z0-9]+", normalized))
        if 1 <= word_count <= 3 and "?" not in normalized:
            return self._extract_standalone_customer_query(normalized)

        return None

    def _clean_name_candidate(self, candidate: str) -> str | None:
        normalized = re.sub(r"\s+", " ", candidate).strip(" .?,")
        if not normalized:
            return None

        words = [
            word
            for word in re.findall(r"[A-Za-z][A-Za-z' -]*", normalized)
            if word.lower().strip("' -") not in QUERY_STOP_WORDS
        ]
        if not words:
            return None

        return " ".join(words[:3]).strip()

    def _extract_likely_name_token(self, message: str) -> str | None:
        words = re.findall(r"[A-Za-z][A-Za-z']*", message)
        candidates = [word for word in words if word.lower() not in QUERY_STOP_WORDS]
        if not candidates:
            return None
        return candidates[0]

    def _answer_remembered_identity_question(self, message: str, session: dict[str, object]) -> str | None:
        normalized = message.lower()
        asks_memory = any(
            phrase in normalized
            for phrase in [
                "what i said my name is",
                "what is my name",
                "my name",
                "remember my name",
                "what phone",
                "my phone",
                "remember my phone",
            ]
        )
        if not asks_memory:
            return None

        customer = session.get("customer")
        customer_data = customer if isinstance(customer, dict) else {}
        remembered_name = customer_data.get("full_name") or customer_data.get("name")
        remembered_phone = customer_data.get("phone")
        remembered_query = session.get("last_customer_query")

        if remembered_name and remembered_phone:
            return f"I remember this customer as {remembered_name}, phone {remembered_phone}."
        if remembered_name:
            return f"I remember the customer name as {remembered_name}."
        if remembered_phone:
            return f"I remember the customer phone as {remembered_phone}."
        if remembered_query:
            return f"I remember you gave me this lookup value: {remembered_query}."

        session["awaiting_customer_query"] = True
        return "I do not have your name or phone number saved yet. Please enter your phone number or part of your name."

    def _answer_from_raw_customer_record(self, message: str, session: dict[str, object]) -> str | None:
        customer = session.get("customer")
        customer_data = customer if isinstance(customer, dict) else {}
        raw_record = customer_data.get("raw_record")
        if not isinstance(raw_record, dict):
            return None

        normalized_message = message.lower()
        if self._is_customer_detail_question(message):
            return "Here is what I have for this customer session: " + self._format_record_summary(raw_record)

        best_key = None
        best_score = 0
        for key in raw_record:
            key_tokens = set(re.findall(r"[a-z0-9]+", str(key).lower()))
            if not key_tokens:
                continue
            score = sum(1 for token in key_tokens if token in normalized_message)
            if score > best_score:
                best_key = str(key)
                best_score = score

        if best_key and best_score > 0:
            value = raw_record.get(best_key)
            if value not in (None, ""):
                return f"{best_key}: {value}"

        return None

    def _format_record_summary(self, raw_record: dict[str, object]) -> str:
        parts = []
        for key, value in raw_record.items():
            if value in (None, ""):
                continue
            parts.append(f"{key}: {value}")
        return "; ".join(parts)

    def _raw_record_for_prompt(self, session: dict[str, object]) -> dict[str, object]:
        customer = session.get("customer")
        customer_data = customer if isinstance(customer, dict) else {}
        raw_record = customer_data.get("raw_record")
        return raw_record if isinstance(raw_record, dict) else {}

    async def _lookup_customer(self, query: str, debug: dict[str, object] | None = None) -> CustomerLookupResult:
        cleaned_query = query.strip()
        url = f"{self.customer_api_url}?{urlencode({'query': cleaned_query})}"
        if debug is not None:
            debug["customer_api_invoked"] = True
            debug["customer_api_url"] = url
            debug["customer_api_query"] = cleaned_query

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.TimeoutException:
            return CustomerLookupResult(
                found=False,
                query=cleaned_query,
                message="The customer lookup service took too long to respond.",
            )
        except httpx.HTTPStatusError as exc:
            return CustomerLookupResult(
                found=False,
                query=cleaned_query,
                message=f"The customer lookup service returned HTTP {exc.response.status_code}.",
            )
        except httpx.HTTPError:
            return CustomerLookupResult(
                found=False,
                query=cleaned_query,
                message="The customer lookup service is currently unavailable.",
            )

        payload = response.json()
        if isinstance(payload.get("matches"), list):
            matches = payload.get("matches") or []
            if not matches:
                return CustomerLookupResult(
                    found=False,
                    query=str(payload.get("query", cleaned_query)),
                    message=str(payload.get("message", "No matching customer was found.")),
                )

            match = matches[0]
            return CustomerLookupResult(
                found=True,
                query=str(payload.get("query", cleaned_query)),
                customer_id=self._pick(match, "customer_id", "Customer ID"),
                loyalty_id=self._pick(match, "loyalty_id", "Loyalty ID"),
                full_name=self._pick(match, "full_name", "name", "Customer Name"),
                phone=self._pick(match, "phone", "Phone Number"),
                loyalty_points=self._pick(match, "loyalty_points", "Loyalty Points"),
                preferred_store=self._pick(match, "preferred_store", "Preferred Store"),
                meal_preference=self._pick(match, "meal_preference", "Meal Preference", "Dietary Preference"),
                coupon=self._build_coupon(match),
                message=payload.get("message"),
                raw_record=match,
            )

        return CustomerLookupResult(
            found=bool(payload.get("found", False)),
            query=str(payload.get("query", cleaned_query)),
            customer_id=self._pick(payload, "customer_id", "Customer ID"),
            loyalty_id=self._pick(payload, "loyalty_id", "Loyalty ID"),
            full_name=self._pick(payload, "full_name", "Customer Name"),
            phone=self._pick(payload, "phone", "Phone Number"),
            loyalty_points=self._pick(payload, "loyalty_points", "Loyalty Points"),
            preferred_store=self._pick(payload, "preferred_store", "Preferred Store"),
            meal_preference=self._pick(payload, "meal_preference", "Meal Preference", "Dietary Preference"),
            coupon=self._build_coupon(payload),
            message=payload.get("message"),
            raw_record=payload,
        )

    def _pick(self, payload: dict[str, object], *keys: str) -> object | None:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value
        return None

    def _build_coupon(self, payload: dict[str, object]) -> dict[str, object] | None:
        existing_coupon = payload.get("coupon")
        if isinstance(existing_coupon, dict):
            return existing_coupon

        coupon = self._pick(payload, "Coupon", "Active Coupon")
        coupon_details = self._pick(payload, "Coupon Details")
        valid_from = self._pick(payload, "Coupon Valid From")
        valid_until = self._pick(payload, "Coupon Valid Until")
        if not any([coupon, coupon_details, valid_from, valid_until]):
            return None

        return {
            "active": self._pick(payload, "Active Coupon"),
            "offer": coupon,
            "details": coupon_details,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }

    def _customer_response_from_data(
        self,
        customer: object,
        intent: str,
        delegated: bool,
        debug: dict[str, object],
        data: dict[str, object] | None = None,
        prefix: str = "",
    ) -> ChatResponse:
        customer_data = customer if isinstance(customer, dict) else {}
        points = customer_data.get("loyalty_points")
        preferred_store = customer_data.get("preferred_store")
        loyalty_id = customer_data.get("loyalty_id")
        meal_preference = customer_data.get("meal_preference")
        coupon = customer_data.get("coupon")
        name = customer_data.get("full_name") or "the matching customer"
        phone = customer_data.get("phone")
        customer_id = customer_data.get("customer_id")
        points_text = f" They currently have {points} loyalty points." if points is not None else ""
        store_text = f" Preferred store: {preferred_store}." if preferred_store else ""
        loyalty_text = f" Loyalty ID: {loyalty_id}." if loyalty_id else ""
        phone_text = f" Phone: {phone}." if phone else ""
        meal_text = f" Meal preference: {meal_preference}." if meal_preference else ""
        coupon_text = ""
        if isinstance(coupon, dict) and coupon:
            offer = coupon.get("offer") or coupon.get("details")
            active = coupon.get("active")
            coupon_text = f" Coupon: {offer}." if offer else ""
            if active:
                coupon_text += f" Active: {active}."

        return ChatResponse(
            answer=(
                f"{prefix}I found customer ID {customer_id} for {name}."
                f"{phone_text}{loyalty_text}{points_text}{store_text}{meal_text}{coupon_text}"
            ),
            intent=intent,
            delegated=delegated,
            data=data or customer_data,
            debug=debug,
        )

    def _debug_session(self, session: dict[str, object]) -> dict[str, object]:
        customer = session.get("customer")
        customer_data = customer if isinstance(customer, dict) else {}
        return {
            "awaiting_customer_query": bool(session.get("awaiting_customer_query", False)),
            "last_customer_query": session.get("last_customer_query"),
            "cached_customer_id": customer_data.get("customer_id"),
            "cached_customer_name": customer_data.get("full_name"),
            "cached_customer_phone": customer_data.get("phone"),
            "identified_customer_id": session.get("identified_customer_id"),
            "identified_customer_query": session.get("identified_customer_query"),
            "raw_record_keys": list((customer_data.get("raw_record") or {}).keys())
            if isinstance(customer_data.get("raw_record"), dict)
            else [],
        }

    def _finish_debug(self, debug: dict[str, object], session: dict[str, object]) -> dict[str, object]:
        debug["session_after"] = self._debug_session(session)
        return debug

    def _answer_grocery_question(self, message: str) -> str:
        normalized = message.lower()

        if any(word in normalized for word in ["hour", "open", "close", "timing"]):
            return f"{self.store_name} is open daily from 8:00 AM to 10:00 PM."

        if any(word in normalized for word in ["delivery", "deliver", "shipping"]):
            return "We offer same-day grocery delivery for nearby addresses and scheduled delivery for later time slots."

        if any(word in normalized for word in ["return", "refund", "exchange"]):
            return "Packaged grocery items can usually be returned within 7 days with a receipt. Fresh produce issues are handled the same day."

        if any(word in normalized for word in ["offer", "discount", "coupon", "sale"]):
            return "Today we have weekly grocery discounts, loyalty member offers, and digital coupons at checkout."

        if any(word in normalized for word in ["milk", "bread", "rice", "egg", "fruit", "vegetable", "produce"]):
            return "Most daily grocery items are available in-store. For exact stock, please share the item name and preferred store location."

        return (
            f"Thanks for contacting {self.store_name}. I can help with store hours, delivery, returns, offers, "
            "product availability, and customer account details."
        )
