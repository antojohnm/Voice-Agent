from groq import Groq
from dotenv import load_dotenv
import os
import re

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

NUMBER_FORMAT_RULE = """
CRITICAL FORMATTING RULE: Whenever you mention any number sequence such as 
an order ID, phone number, or reference number, ALWAYS space out each digit 
individually. For example:
- Order ID 90000000002 → say "9 0 0 0 0 0 0 0 0 0 2"
- Phone 9876543210 → say "9 8 7 6 5 4 3 2 1 0"
- 452819 → "4 5 2 8 1 9"
- 1234 → "1 2 3 4"
Short numbers like prices ($49.99), quantities (3 items), 
and years (2026) must be said naturally."""

SYSTEM_PROMPT_UNVERIFIED = """You are a customer support agent.
You are polite, professional and concise.
Keep all responses under 2 sentences — this is a voice call.
""" + NUMBER_FORMAT_RULE + """

You do not have the customer's order details yet.
Ask the customer for their Order ID to proceed.
Do not reveal or guess any order information until the Order ID is provided."""

SYSTEM_PROMPT_VERIFIED = """You are a customer support agent.
You are polite, professional and concise.
Keep all responses under 2 sentences — this is a voice call.
""" + NUMBER_FORMAT_RULE + """

The ORDER ID is the number under 'ORDER ID:' in the data below.
Never refer to the phone number as an order ID.
Never read out the customer's phone number unless explicitly asked.

The customer's full details are below. Use only this data to answer their questions.
Never reveal another customer's data. If asked something not in this data, tell the user to 
ask only about order related queries that they might have.

{order_context}"""


def extract_order_id(text):
    """Extract a numeric order ID from speech"""
    # Match standalone numbers (order IDs in your schema are integers)
    matches = re.findall(r'\b(\d{1,10})\b', text)
    if matches:
        return int(matches[0])
    return None


def chat(user_message, call_sid=None):
    from database import (
        get_conversation_history, save_message,
        get_order_context, get_verified_order,
        save_verified_order
    )

    # Save user message
    if call_sid:
        save_message(call_sid, "user", user_message)

    conversation_history = get_conversation_history(call_sid) if call_sid else []
    conversation_history = [m for m in conversation_history if m["role"] != "system"]

    # Check if order already identified for this call
    verified_order_id = get_verified_order(call_sid) if call_sid else None

    if verified_order_id:
        # Already identified — pull fresh data and inject into prompt
        order_context = get_order_context(int(verified_order_id))
        system_prompt = SYSTEM_PROMPT_VERIFIED.format(order_context=order_context)
        print(f"[{call_sid}] Using order context for order ID: {verified_order_id}")

    else:
        # Try to extract order ID from current message
        order_id = extract_order_id(user_message)

        if order_id:
            order_context = get_order_context(int(order_id))

            if order_context:
                # Valid order found — save and use it
                save_verified_order(call_sid, str(order_id))
                system_prompt = (
                    "You are a customer support agent. Be polite, professional and concise. "
                    "Keep all responses under 2 sentences — this is a voice call.\n\n"
                    "The customer just provided their Order ID and it was found. "
                    "Greet them by their name from the data below and ask how you can help.\n\n"
                    + order_context
                )
                print(f"[{call_sid}] Order {order_id} found and loaded.")
            else:
                # Order ID given but not found in database
                system_prompt = (
                    "You are a customer support agent. Be polite and concise. "
                    "Keep all responses under 2 sentences — this is a voice call.\n\n"
                    "The customer provided an Order ID but it was not found in the system. "
                    "Apologize and ask them to check their order confirmation and try again."
                )
                print(f"[{call_sid}] Order ID {order_id} not found in database.")
        else:
            # No order ID yet — keep asking
            system_prompt = SYSTEM_PROMPT_UNVERIFIED

    conversation_history.insert(0, {"role": "system", "content": system_prompt})
    conversation_history.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=conversation_history,
        max_tokens=100,
        temperature=0.3
    )

    reply = response.choices[0].message.content

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
