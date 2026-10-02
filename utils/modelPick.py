# With this i just need to pass the level of the model in anywhere , and call thid function like this -> check =model_pick("low")

from langchain_ollama import ChatOllama
def model_pick(level:str):
    if level.lower() =="low":
        return ChatOllama(
            model="gemma4:e2b",
            temperature=0.0
        )
    elif level.lower() =="mid":
        return ChatOllama(
            model="gemma4:e2b",
            temperature=0.5
        )
    elif level.lower() =="high":
        return ChatOllama(
            model="gemma4:e2b",
            temperature=1.0
        )
    else:
        raise ValueError(f"Invalid level {level} Please provide valid level")
    
    

    