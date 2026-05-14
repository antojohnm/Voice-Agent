from groq import Groq
from dotenv import load_dotenv
import os
import re
from datetime import date
import calendar

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def detect_sentiment(text: str) -> str:
    """Simple keyword-based sentiment detection."""
    text_lower = text.lower()

    angry_words = ["ridiculous", "useless", "terrible", "worst", "angry",
                   "furious", "unacceptable", "disgusting", "pathetic", "stupid"]
    frustrated_words = ["frustrated", "annoyed", "fed up", "tired", "again",
                        "still", "waiting", "long", "delay", "why"]
    worried_words = ["worried", "concern", "scared", "afraid", "lost",
                     "missing", "wrong", "problem", "issue", "help"]
    cancel_words = ["cancel", "refund", "return", "quit", "done", "leave"]

    if any(word in text_lower for word in angry_words):
        return "ANGRY"
    elif any(word in text_lower for word in cancel_words):
        return "THREATENING_TO_CANCEL"
    elif any(word in text_lower for word in frustrated_words):
        return "FRUSTRATED"
    elif any(word in text_lower for word in worried_words):
        return "WORRIED"
    else:
        return "NEUTRAL"


NUMBER_FORMAT_RULE = """
CRITICAL FORMATTING RULE: Whenever you mention any number sequence such as 
an order ID, phone number, or reference number, ALWAYS space out each digit 
individually. For example:
- Order ID 1001 → say "1 0 0 1"
- Phone 9876543210 → say "9 8 7 6 5 4 3 2 1 0"

NEVER space out the following — say them naturally:
- Prices ($49.99, $150)
- Quantities (3 items, 2 units)
- Years (2026, 2025)
- Dates and ordinals (May 10th, the 5th, 3rd of June)
- Days of the month (10th, 21st, 3rd)
- Delivery timeframes (in 2 days, 3 weeks)
"""

PERSONALITY_RULES = """
PERSONALITY AND TONE:
- You are warm, empathetic, and genuinely helpful — not robotic or scripted
- Speak naturally like a real human support agent would on a phone call
- Use natural conversational phrases like "Of course", "Absolutely", "I understand", "Let me check that for you"
- Never start two consecutive responses with the same word or phrase
- Vary your language — don't repeat the same phrases every turn
- Keep responses concise — this is a voice call, not a chat

EMOTIONAL INTELLIGENCE:
- Always acknowledge the customer's emotion BEFORE answering their question
- If the customer sounds frustrated: acknowledge it first — "I completely understand your frustration, and I'm going to do my best to help you right now."
- If the customer sounds angry: stay calm, never match their anger, lower your tone — "I sincerely apologise for this experience. Let me look into this immediately."
- If the customer sounds upset or worried: show empathy — "I can hear that this is concerning for you, and I want to make sure we sort this out together."
- If the customer is calm and polite: be warm and friendly — match their energy
- Never be dismissive, defensive, or robotic when emotions are high
- Never say "I cannot help with that" bluntly — always offer an alternative or escalate

HANDLING DIFFICULT SITUATIONS:
- If the customer threatens to cancel: acknowledge their frustration, apologise sincerely, and offer to escalate
- If the customer uses harsh language: stay calm and professional
- If the customer repeats the same question: rephrase your answer differently
- If the customer asks something you cannot answer: be honest but helpful
- If the customer is confused: slow down, simplify, and guide them step by step

WHAT TO NEVER DO:
- Never say "I'm just an AI" or reveal you are an AI unless directly asked
- Never say "I cannot", "I'm unable to", "That's not possible" without offering an alternative
- Never sound impatient or dismissive
- Never give the same response twice in a row
- Never ignore an emotional statement to jump straight to facts
- Never use corporate jargon like "per our policy", "as per records", "kindly note"
"""
PRODUCT_QUERY_RULES = """
HANDLING PRODUCT-SPECIFIC QUERIES — VERY IMPORTANT:

When a customer asks about ANY of the following topics WITHOUT specifying a product or category:
- Promotions, offers, discounts, deals, sales
- Return or refund policies
- Warranty or guarantee information
- Exchange policies

YOU MUST follow this exact approach:

STEP 1 — Ask them to specify first. Never list all products or all offers at once.
Examples of what to say:
- "Of course! Could you tell me which product or category you're asking about?"
- "Absolutely, I can help with that. Which product are you interested in?"
- "Sure! Are you asking about a specific product, or a particular category?"

STEP 2 — Once they specify a product or category, answer ONLY for that product or category.

STEP 3 — If the customer already mentioned a specific product, answer directly without asking again.

EXAMPLES:
✅ Customer: "Do you have any offers?"
   Agent: "Absolutely! Could you tell me which product or category you're interested in?"

✅ Customer: "What is the return policy for the MacBook Air?"
   Agent: [answer directly — product already specified]

✅ Customer: "What are your laptop offers?"
   Agent: [answer directly — category already specified]

❌ NEVER list all products or all offers unprompted.

{product_categories}
"""
SYSTEM_PROMPT_GENERAL = """You are Maya, a friendly and professional customer support agent.
This is a voice phone call — keep all responses under 2 sentences.
""" + PERSONALITY_RULES + """
""" + NUMBER_FORMAT_RULE + """
""" + PRODUCT_QUERY_RULES + """

YOUR NAME: Maya
YOU WORK FOR: A retail electronics company

WHAT YOU CAN HELP WITH RIGHT NOW (no order ID needed):
- Current promotions, offers, discounts and deals
- Return and refund policies
- Warranty information
- Store locations and timings
- General product questions and availability

WHAT REQUIRES AN ORDER ID:
- Order status and tracking
- Delivery updates
- Payment status
- Order-specific return or refund requests

GREETING BEHAVIOUR:
- Warmly introduce yourself as Maya on the first turn
- Do NOT ask for an order ID upfront — let the customer lead
- If the customer asks about their order, delivery, or anything order-specific
  → then ask for their order ID naturally

CRITICAL DATA RULES:
- ONLY use information explicitly provided in this prompt
- NEVER invent offers, policies, or store details from memory
- If no data is provided for a query → ask which product/category first

{additional_context}"""

SYSTEM_PROMPT_UNVERIFIED = """You are Maya, a warm and professional customer support agent.\n"
    "This is a voice phone call — keep all responses under 2 sentences.\n"
    + PERSONALITY_RULES
    + NUMBER_FORMAT_RULE
    + dynamic_product_rules
    + "\nYou do not have the customer's order details yet.\n"
    "Greet the customer warmly and ask for their Order ID to proceed.\n"
    "Do not reveal or guess any order information until the Order ID is provided.\n"
    "If the customer seems frustrated before even giving their order ID, acknowledge it first."""

SYSTEM_PROMPT_ASKING_ORDER_ID = """You are Maya, a friendly and professional customer support agent.
This is a voice phone call — keep all responses under 2 sentences.
""" + PERSONALITY_RULES + """
""" + NUMBER_FORMAT_RULE + """

The customer needs help with something that requires their Order ID.
You have already asked them for it or are about to.
Ask them to say their Order ID clearly, digit by digit.
Do not ask for anything else yet."""


SYSTEM_PROMPT_VERIFIED = """You are Maya, a warm and professional customer support agent.
This is a voice phone call — keep all responses under 2 sentences.
""" + PERSONALITY_RULES + """
""" + NUMBER_FORMAT_RULE + """
""" + PRODUCT_QUERY_RULES + """

TODAY'S DATE: {today_date}

Use today's date to answer relative time questions accurately:
- If customer asks "will it arrive tomorrow?" → compare expected delivery date with tomorrow's date
- If customer asks "will it arrive in 2 days?" → calculate from today
- If expected delivery date has already passed and order not delivered → acknowledge the delay empathetically
- Always say the delivery date naturally like "this Friday" or "in 2 days" when possible
- If today is the expected delivery date → tell the customer it should arrive today

The ORDER ID is the number under 'ORDER ID:' in the data below.
Never refer to the phone number as an order ID.
Never read out the customer's phone number unless explicitly asked.
Use only the data below to answer questions.
If asked something outside this data, say you can only help with order related queries
and offer to connect them to a specialist if needed.

CRITICAL DATA RULES — NEVER VIOLATE:
- ONLY use information explicitly provided below in this prompt
- NEVER invent offers, policies, or order details from memory
- Every fact you state must come directly from the data below

The ORDER ID is the number under ORDER ID in the data below.
Never refer to the phone number as an order ID.
Never read out the customer's phone number unless explicitly asked.

{order_context}
{additional_context}"""

def needs_order_id(text: str) -> bool:
    """
    Returns True if the customer's message requires an order ID to answer.
    These are queries that are specific to their personal order.
    """
    order_triggers = [
        "my order", "my delivery", "my package", "my item",
        "track", "tracking", "where is my", "when will my",
        "order status", "delivery status", "delivery date",
        "my payment", "my refund", "my return",
        "i ordered", "i purchased", "i bought",
        "hasn't arrived", "not delivered", "not received",
        "cancel my order", "change my order",
        "order number", "order id", "order details"
    ]
    text_lower = text.lower()
    return any(trigger in text_lower for trigger in order_triggers)

def extract_order_id(text):
    """Extract a numeric order ID from speech"""
    matches = re.findall(r'\b(\d{1,10})\b', text)
    if matches:
        return int(matches[0])
    return None


def get_today_string():
    """Get today's date as a natural string"""
    today = date.today()
    day_name = calendar.day_name[today.weekday()]
    return f"{day_name}, {today.strftime('%B %d, %Y')}"


def build_additional_context(user_message):
    """
    Check if the customer's message needs extra context beyond order data.
    Pulls offers, return policy, warranty, or store info as needed.
    Returns additional context string or empty string.
    """
    from database import (
        get_product_offers, get_return_policy,
        get_warranty, get_store_info
    )

    additional_context = ""
    msg_lower = user_message.lower()

    # Offers and promotions
    if any(w in msg_lower for w in ["offer", "discount", "deal", "promotion", "sale"]):
        offers = get_product_offers()
        if offers:
            additional_context += f"\n\n{offers}"

    # Return and refund policy
    if any(w in msg_lower for w in ["return", "refund", "send back", "exchange"]):
        return_policy = get_return_policy()
        if return_policy:
            additional_context += f"\n\n{return_policy}"

    # Warranty information
    if any(w in msg_lower for w in ["warranty", "guarantee", "repair", "damage"]):
        warranty = get_warranty()
        if warranty:
            additional_context += f"\n\n{warranty}"

    # Store information
    if any(w in msg_lower for w in ["store", "shop", "location", "branch", "timing", "open", "close"]):
        city = None
        known_cities = ["chennai", "mumbai", "bangalore", "delhi", "kolkata", "hyderabad"]
        for city_name in known_cities:
            if city_name in msg_lower:
                city = city_name
                break
        store_info = get_store_info(city)
        if store_info:
            additional_context += f"\n\n{store_info}"

    return additional_context


def chat(user_message, call_sid=None):
    from database import (
        get_conversation_history, save_message,
        get_order_context, get_order_context_cached,
        get_verified_order, save_verified_order,
        get_product_categories
    )
    from datetime import date
    import calendar

    # ── Step 1: Save user message ──
    if call_sid:
        save_message(call_sid, "user", user_message)

    # ── Step 2: Get conversation history ──
    conversation_history = get_conversation_history(call_sid) if call_sid else []
    conversation_history = [m for m in conversation_history if m["role"] != "system"]

    # ── Step 3: Detect sentiment ──
    sentiment = detect_sentiment(user_message)
    sentiment_instruction = ""
    if sentiment != "NEUTRAL":
        sentiment_instruction = (
            f"\nIMPORTANT: Customer appears {sentiment}. "
            f"Acknowledge their emotion with empathy before answering.\n"
        )

    # ── Step 4: Build additional context for this message ──
    additional_context = build_additional_context(user_message)

    # ── Step 5: Determine which system prompt to use ──
    verified_order_id = get_verified_order(call_sid) if call_sid else None

    if verified_order_id:
        # ── VERIFIED: Full order context available ──
        order_context = get_order_context_cached(int(verified_order_id), call_sid)
        today = date.today()
        day_name = calendar.day_name[today.weekday()]
        today_str = f"{day_name}, {today.strftime('%B %d, %Y')}"

        system_prompt = SYSTEM_PROMPT_VERIFIED.format(
            today_date=today_str,
            order_context=order_context,
            additional_context=additional_context
        ) + sentiment_instruction

        print(f"[{call_sid}] Order: {verified_order_id} | "
              f"Sentiment: {sentiment} | Today: {today_str}")

    else:
        # ── Try to extract order ID from current message ──
        order_id = extract_order_id(user_message)

        if order_id:
            order_context = get_order_context(int(order_id))

            if order_context:
                # Valid order found — verify and switch to verified mode
                save_verified_order(call_sid, str(order_id))
                today = date.today()
                day_name = calendar.day_name[today.weekday()]
                today_str = f"{day_name}, {today.strftime('%B %d, %Y')}"

                system_prompt = (
                    "You are Maya, a warm and professional customer support agent. "
                    "Keep all responses under 2 sentences — this is a voice call.\n\n"
                    + PERSONALITY_RULES + "\n"
                    + NUMBER_FORMAT_RULE + "\n\n"
                    "The customer just provided their Order ID and it was found. "
                    "Greet them warmly by their first name and confirm their order is loaded. "
                    "Ask how you can help with their order.\n\n"
                    + order_context
                )
                print(f"[{call_sid}] Order {order_id} found and verified.")

            else:
                # Order ID given but not found
                system_prompt = (
                    "You are Maya, a warm and professional customer support agent. "
                    "Keep all responses under 2 sentences — this is a voice call.\n\n"
                    "The customer provided an Order ID but it was not found. "
                    "Apologise warmly and ask them to double-check and try again."
                )
                print(f"[{call_sid}] Order ID {order_id} not found.")

        elif needs_order_id(user_message):
            # Customer is asking about their order but hasn't given ID yet
            system_prompt = SYSTEM_PROMPT_ASKING_ORDER_ID + sentiment_instruction
            print(f"[{call_sid}] Order ID required — prompting customer")

        else:
            # General query — no order ID needed
            system_prompt = SYSTEM_PROMPT_GENERAL.format(
                additional_context=additional_context if additional_context else
                "\n\nNo specific product data loaded yet. "
                "If customer asks about offers or policies, ask which product first."
            ) + sentiment_instruction
            print(f"[{call_sid}] General query | Sentiment: {sentiment}")

    # ── Step 6: Call LLM ──
    conversation_history.insert(0, {"role": "system", "content": system_prompt})
    conversation_history.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=conversation_history,
        max_tokens=60,
        temperature=0.3
    )

    reply = response.choices[0].message.content

    # ── Step 7: Save reply ──
    if call_sid:
        save_message(call_sid, "assistant", reply)

    return reply


if __name__ == "__main__":
    print("Customer Support Agent Ready. Type 'quit' to exit.\n")
    while True:
        user_input = input("You: ")
        if user_input.lower() == "quit":
            break
        response = chat(user_input)
        print(f"Agent: {response}\n")
