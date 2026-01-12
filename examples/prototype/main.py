import os
import sys
from agent import Agent
import json

def main():
    if len(sys.argv) <= 1:
        print("No command line args provided!")
        return
    
    instructionsPath = sys.argv[1]
    # check if we have a valid file path
    if (not os.path.exists(instructionsPath)):
        print(f"The path does not exist: {instructionsPath}\n")
        content = ""
    else:
        with open(instructionsPath, 'r') as f:
            content = f.read()

    agent = Agent(content)


    file = input(f"{"\033[32m"}user: {"\033[0m"}")

    data = json.loads(agent.message(file))

    with open('semantics.json', 'w') as jf:
        json.dump(data, jf, indent=4)
    
main()