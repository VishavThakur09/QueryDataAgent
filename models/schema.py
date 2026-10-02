from pydantic import BaseModel, Field
from typing import Annotated, List, Literal
from operator import add
# This is the sample code how the state work kaha se kya ho raha ha for he understanding --->

# User asks: "show me top 5 customers"
#urated_question = "Show me the top 5 customers by total purchase amount"
# ↑ cleaned up version of user input

# prompt_context = """
# You are a SQL expert. Given this database schema:
#   Table: customers (id, name, email)
#   Table: orders (id, customer_id, amount)
# Generate a SQL query for: "Show me the top 5 customers by total purchase amount"
# Rules: Only use SELECT. No DROP/DELETE/UPDATE.
# """
# # ↑ YOU build this → then SEND to LLM

# ai_generated_sqlQuery = """
# SELECT c.name, SUM(o.amount) as total
# FROM customers c
# JOIN orders o ON c.id = o.customer_id
# GROUP BY c.name
# ORDER BY total DESC
# LIMIT 5
# """
# # ↑ LLM returns this

# sql_result = '[{"name":"Alice","total":5000},{"name":"Bob","total":4200}]'
# # ↑ you run the query → store result here
# final_response = "The top 5 customers by purchase are: 1. Alice ($5000) ..."
# # ↑ LLM formats sql_result into a nice answer


class AgentSchema(BaseModel):
    messages: Annotated[List,add]=Field(...,description="List of the messages are provides")
    user_question:str=Field(...,description="User question")
    curated_question:str=Field(...,description="Final curated question")
    prompt_context:str =Field(...,description="A detailed prompt with the SQl query context")
    ai_generated_sqlQuery:str=Field(...,description="AI generated sql query with the curated question and the prompt context")
    is_safe:Literal["YES","NO"]=Field(...,description="Is this prompt safe to be executed in the database")
    comments:str =Field(...,description="Here we have the comments after checking hte generated sql query.")
    sql_result:str=Field(...,description="Result of the sql query")
    final_response:str=Field(...,description="Final response to the user")


class structureJudgeSqlSchema(BaseModel):
    answer:Literal["YES","NO"]=Field(...,description="Answer YES if the SQL query is SAFE to execute (SELECT only). Answer NO if it is UNSAFE (contains DROP, DELETE, UPDATE, INSERT, TRUNCATE).")
    comment: str =Field(...,description="Briefly explain why the query is safe or unsafe.")


class etl_structure_schema(BaseModel):
    messages :Annotated[list,add]=Field(...,description="List of the messages are provides in the etl agent")
  
    
    