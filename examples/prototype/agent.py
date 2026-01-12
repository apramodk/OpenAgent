'''
a class wrapper which does the following:
- initializes an llm api
- initializes an array of strings to maintain conversation history
'''
import os
import sys
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient


class Agent:
    def __init__(self, instructions):
        load_dotenv()

        project_client = AIProjectClient(
            endpoint=os.environ['PROJECT_ENDPOINT'],
            credential=DefaultAzureCredential(),
        )

        self.llm = project_client.get_openai_client()
        self.messages = []

        if instructions != "":
            self.messages.append({"role": "system", "content": instructions})

    def message(self, file):
        msg = ""
        if (not os.path.exists(file)):
            return "Not a valid File"

        with open(file, 'r') as f:
            msg = f.read()

        self.messages.append({"role": "user", "content": {"filename": file, "content": msg}})

        response = self.llm.responses.create(
            model=os.environ['MODEL_DEPLOYMENT_NAME'],
            input=str(self.messages)
        )

        self.messages.append({"role": "assistant", "content": response.output_text})
        return response.output_text

    def getChatHistory(self):
        return self.messages