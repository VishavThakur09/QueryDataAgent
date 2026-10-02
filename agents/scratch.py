
 # This is the practice for the checking the safe query 
import os
from dotenv import load_dotenv
from utils.modelPick import model_pick
from models.schema import AgentSchema,structureJudgeSqlSchema
from langchain_core.messages import HumanMessage, AIMessage
from utils.database import DatabaseUtils


# this for the structure outpuit for the checking the query is safe or not .FileExistsError
llm = model_pick("medium")

llm_judge = llm.with_structured_output(structureJudgeSqlSchema) # this is the way to make the output in the structure

prompt =f"""
you are the SQL judge for data security. your task is to check the generated the sql query is correct or safe to  execute .
and the sql is used for the data retrival  not for the data updatre keep in mind , and not harmful.
and your response in the given format which we proive you , dont add the external commnet or the irrelevant information.
and her eis the sql query :
{sqlquery}

"""

response = llm_judge.invoke(prompt).model_dump()