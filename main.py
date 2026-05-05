import time
from stt import listen
from llm import chat
from tts import speak

def run_agent():
    print("=" * 50)
    print("AI Customer support Agent")
    print("=" * 50)
    print("Speak after the prompt. Say 'goodbye' to end.\n")

    greeting = "Hello! Welcome to customer support. How can I help you today?"

    print(f"Agent: {greeting}")
    speak(greeting)

    while True:
        print("\n" + "-" *30)

        input("Press ENTER to speak...")
        user_text = listen()

        if not user_text:
            print("Didn't catch that, please try again.")
            continue

        print(f"You said: {user_text}")

        if any(word in user_text.lower() for word in ["goodbye", "bye", "exit", "quit"]):
            farewell = "Thankyou for calling. Have a great day. Goodbye!"
            print(f"Agent: {farewell}")
            speak(farewell)
            break

        print("Agent thinking...")
        response = chat(user_text)
        print(f"Agent: {response}")

        speak(response)

if __name__ == "__main__":
    run_agent()
