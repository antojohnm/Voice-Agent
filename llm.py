from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

conversation_history = [
    {
        "role" : "system",
        "content": """You are a helpful customer support agent.
        You are polite, professional and consise.
        Keep all responses under 2 sentences- this is a voice call.
        Always greet the customer when they first call."""
    }
]

def chat(user_message):
    conversation_history.append({
        "role" : "user",
        "content": user_message
    })

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=conversation_history,
        max_tokens=150,
        temperature=0.3
    )

    reply = response.choices[0].message.content
    conversation_history.append({
        "role": "assistant",
        "content": reply
    })

    return reply

if __name__ == "__main__":
    print("Customer Support Agent Ready. Type 'quit' to exit.\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() == "quit":
            break

        response = chat(user_input)
        print(f"Agent: {response}\n")