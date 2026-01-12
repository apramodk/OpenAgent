import dspy
import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

class ExtractIntent(dspy.Signature):
    """Extract user intent and determine next action."""
    
    user_input: str = dspy.InputField()
    context: str = dspy.InputField(default="")
    
    intent: str = dspy.OutputField(desc="What the user wants")
    entities: str = dspy.OutputField(desc="Key terms mentioned")
    action: str = dspy.OutputField(desc="search, clarify, or answer")
    query: str = dspy.OutputField(desc="Search query if action is search")

class CoTAgent:
    def __init__(self):
        load_dotenv()
        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default").token

        # dspy needs the azure endpoint not the foundry endpoint
        lm = dspy.LM(
            f"azure/{os.environ['MODEL_DEPLOYMENT_NAME']}",
            api_key=os.environ['AZURE_KEY'],
            api_base=os.environ['PROJECT_ENDPOINT_OAI'],
            api_version="2024-02-01"
        )
        dspy.configure(lm=lm)
        
        self.extract_intent = dspy.ChainOfThought(ExtractIntent)
    
    def plan(self, user_input, context=""):
        result = self.extract_intent(user_input=user_input, context=context)
        return {
            "intent": result.intent,
            "entities": result.entities,
            "action": result.action,
            "query": result.query,
            "reasoning": result.reasoning  # CoT gives you this for free
        }

if __name__ == "__main__":
    agent = CoTAgent()
    
    userResponse = input("user: ")
    plan = agent.plan(userResponse)
    print(f"\n")
    print(f"\nIntent: {plan['intent']}")
    print(f"\nAction: {plan['action']}")
    print(f"\nQuery: {plan['query']}")
    print(f"\nReasoning: {plan['reasoning']}")