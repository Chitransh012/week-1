import os
import sys
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
class ChatAgent:
    def __init__(self,model_name:str,system_prompt:str="you are nice agent please give reply in 2 sentences",max_turns:int=10):
        api_key_check = os.environ.get("OPENROUTER_API_KEY")
        if not api_key_check:
            print("'OPENROUTER_API_KEY' was not found in your environment.")
            sys.exit(1)

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key_check,
        )

        self.model_name=model_name
        self.system_prompt=system_prompt
        self.max_turns=max_turns
        self.messages=[{"role":"system","content":self.system_prompt}]
        self.last_usage=None
    def call_model(self):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages               
            )
            return response
        except Exception as E:
            print(f"RAW API ERROR: {E}")
            return None
    def verify_response_accuracy(self, user_prompt: str, ai_reply: str) -> bool:
        context_messages = list(self.messages)
        context_messages.append({"role": "assistant", "content": ai_reply})
        validation_instruction = (
            "You are a strict quality control validator reviewing an ongoing chat transcript thread. "
            "Look at the absolute LAST assistant message in the conversation history log. "
            "Determine if that final assistant message is a genuinely valid, logical, and accurate response "
            "based on the prior context provided in the history logs. "
            "If it is a server glitch (like 'safe'), empty, or violates historical facts, it is INVALID. "
            "Respond with EXACTLY one word: 'CORRECT' if the answer is accurate to the context, or 'INCORRECT' if it fails."
        )
        context_messages.insert(0, {"role": "system", "content": validation_instruction})
        
        try:
            check_response = self.client.chat.completions.create(
                model="openrouter/free",
                messages=context_messages
            )
            verdict = check_response.choices[0].message.content.strip().upper()  
            if"INCORRECT" not in verdict:
                return True
            else:
                return False
        except Exception:
            return True

    def rolling_buffer(self):
        max_numberof_messages=1+(self.max_turns*2)
        if len(self.messages)>=max_numberof_messages:
            print("[SYSTEM]: History threshold crossed. Compacting log context...")
            history_to_compact=self.messages[1:]
            transcript=""
            for msg in history_to_compact:
                role_label="user" if msg["role"]=="user" else "assistant"
                transcript+=f"{role_label}:{msg['content']}\n"
            summary_prompt=[{"role":"system","content":"please summarise these chat logs into 1 single clean sentence"},
                            {"role":"user","content":transcript}
                            ]
            try:
                summary_response=self.client.chat.completions.create(
                    model="openrouter/free",
                    messages=summary_prompt
                )
                summary=summary_response.choices[0].message.content
                self.messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"[Historical Context Recap: {summary}]"},
                    {"role": "assistant", "content": "I have successfully recorded the summary context into my active memory. Please continue!"}
                ]
                print("[SYSTEM]: History compacted successfully!\n")
            except Exception as E:
                print("Some Error Occured In Compacting")
        else:
            return
    def start_ai(self):
        while True:
            prompt=input("Enter Prompt:").strip()
            if prompt.lower() in["exit","quit"]:
                print("Thanks for using our service")
                break
            if prompt=="/clear":
                self.messages=[{"role":"system","content":self.system_prompt}]
                self.last_usage=None
                print("new chat started,previous history deleted")
                continue
            if prompt=="/tokens":
                if self.last_usage:
                    prompt_tokens = self.last_usage.prompt_tokens
                    completion_tokens = self.last_usage.completion_tokens
                    total_tokens = self.last_usage.total_tokens
                    print(f"Prompt tokens:{prompt_tokens},Completion tokens:{completion_tokens},Total tokens:{total_tokens}")
                else:
                    print("Not Enough Conversation Made To See Tokens")
                continue
            if prompt=="/compact":
                self.rolling_buffer()
                continue
            if not prompt:
                continue
            self.rolling_buffer()
            self.messages.append({"role":"user","content":prompt})
            print("Thinking...")
            response=self.call_model()
            if not response:
                self.messages.pop()
                print("I could not understand that")
                continue
            reply=response.choices[0].message.content
            if not self.verify_response_accuracy(prompt,reply):
                self.messages.pop()
                print("Some unknown Glitch occured while fetchign answer")
                print("please re-enter your prompt")
                continue                
            self.last_usage = response.usage
            self.messages.append({"role":"assistant","content":reply})
            print(f"AI:{reply}")


if __name__=="__main__":
        print("Hello, commands: /clear : start new chat | /compact : compact history | /tokens : see number of tokens used | exit or quit : exit chat")
        print("Please choose your model from:")
        print("1.OpenRouter Universal Free Fallback")
        print("2.Google Gemini Flash Free")
        print("3.DeepSeek Flash Free")
        choice=input("Enter Your Choice Number of Model.eg 2 for google gemini free: ").strip()
        model= "openrouter/free"
        if choice=="2":
            print("Google Gemini activated")
        elif choice=="3":
            print("Deepseek activated")
        else:
            print("Openrouter free activated")
        agent=ChatAgent(model_name=model,max_turns=2)
        agent.start_ai()








