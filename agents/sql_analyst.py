import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
from dotenv import load_dotenv
from utils.modelPick import model_pick
from models.schema import AgentSchema,structureJudgeSqlSchema
from langchain_core.messages import HumanMessage, AIMessage
from utils.database import DatabaseUtils
from langgraph.graph import StateGraph,END,START

load_dotenv()

def curateQuery(state:AgentSchema)->dict:
    userQuestion = state.user_question
    llm = model_pick('low')
    response = llm.invoke(
        f"""Rewrite the following user question as a single clear and concise sentence suitable for querying a database.
        
        Rules:
        - Return ONLY the rewritten question as a single sentence.
        - Do NOT add explanations, options, or extra text.
        - Do NOT add bullet points or headings.
        - Just one clean sentence, nothing else.
        
        User question: {userQuestion}
        
        Rewritten question:"""
    )
    return {
        "curated_question": response.content,
        "messages": [HumanMessage(content=response.content)]
    }


# Here we make this function or the agent to connect the database with the curatedQuestion and make the final proper prompt.
def prompt_with_sqlContext(state: AgentSchema) -> dict:
    curatedQuestion = state.curated_question

    connection_detail = {
        "host":     os.getenv("host"),
        "user":     os.getenv("user"),
        "password": os.getenv("passward"),
        "dbname":   os.getenv("database"),
        "port":     os.getenv("port", "5432"),
    }
    db_object   = DatabaseUtils(connection_detail)
    schema_info = db_object.schema_details("public")

    prompt = f"""
    You are an SQL analyst agent. Your task is to convert the user's natural language
    query into Postgres SQL query that can be executed on the database. You are provided
    with the user's original query and the schema details of the database, including
    table names, column names, data types, and sample data for each table so that
    you can understand the structure of the database and generate an accurate SQL query.
    Unless user explicitly asks for specific number of rows, always limit the output to 10 rows.
    Note - Just generate the SQL query without any explanation or additional text because
    this query will be executed directly on the database. So, the output should be SQL
    ready to be executed without any modifications.

    User's Original Query: {curatedQuestion}

    Database Schema Details:
    {schema_info}
    """
    return {"prompt_context": prompt}


# This is for Generation the sql query
def generated_sql_query(state:AgentSchema)->dict:
    prompt = state.prompt_context
    llm = model_pick('high')
    generate_sql_query = llm.invoke(prompt)
    return {
        "ai_generated_sqlQuery": generate_sql_query.content,
        "messages": [AIMessage(content=generate_sql_query.content)]
    }



# make the fucntion or the node for judging the prompt is safe or not --->( make the struturw output
# now we are creating the  safe node after the genaration the aiGenerated_sqlQuery node --
def safe_node_sql(state: AgentSchema)->dict:
    sqlQuery = state.ai_generated_sqlQuery
    llm = model_pick('mid')
    llm_judge = llm.with_structured_output(structureJudgeSqlSchema)

    prompt = f"""
    You are a SQL security judge. Analyze the SQL query below and decide if it is safe to execute.

    Rules:
    - Answer "YES" if the query is SAFE (only SELECT statements for data retrieval).
    - Answer "NO" if the query is UNSAFE (contains DROP, DELETE, UPDATE, INSERT, TRUNCATE, or any data modification).
    - A plain SELECT query is ALWAYS safe → answer "YES".
    - Joins, GROUP BY, COUNT, AVG, SUM in a SELECT query are ALWAYS safe → answer "YES".

    SQL Query to judge:
    {sqlQuery}
    """
    response = llm_judge.invoke(prompt)
    return {
        "is_safe": response.answer,
        "comments": response.comment
    }
    


# NOW we have the No answer then we just end the agent and return the comment -- *(Here we add the Conditional node in the graph in NEXT STEPS)
def safeNode_sql_exit(state:AgentSchema)->dict:
    comment = state.comments
    final_response = f"Warning: The query was not safe to execute. Reason: {comment}"
    return {
        "final_response": final_response,
        "messages": [AIMessage(content=final_response)]
    }


# Execute in the postgress-
# NOW we have the YES anwer then run this ->( THis is also the conditional node inthe next steps --just telling you )
def safeNdoe_sql_execute(state:AgentSchema)->dict: # Here we execute in the psotgress
    sql_query = state.ai_generated_sqlQuery

    connection_detail = {
        "host":     os.getenv("host"),
        "user":     os.getenv("user"),
        "password": os.getenv("passward"),
        "dbname":   os.getenv("database"),
        "port":     os.getenv("port", "5432"),
    }
    db_object   = DatabaseUtils(connection_detail)
    sql_result = db_object.execute_query(sql_query)
    return {"sql_result": sql_result}    



# FINAL Represent answer node --->
def final_answer_node(state: AgentSchema) -> dict:
    sql_result = state.sql_result
    curated_question = state.curated_question
    llm = model_pick("high")

    prompt = f"""
    You are a helpful data analyst assistant. A user asked a question and we retrieved
    data from the database. Your job is to present the answer in a clear, well-organized,
    and human-friendly format.

    Rules:
    - DO NOT show any SQL queries in your response.
    - DO NOT mention anything about the database or how the data was fetched.
    - Present the data in a clean format (use bullet points, numbered lists, or a table if needed).
    - Keep the answer concise and directly relevant to the user's question.
    - If the result is empty, politely say no data was found.

    User's Question: {curated_question}

    Data Retrieved from Database: {sql_result}

    Now write a clean, well-formatted final answer for the user:
    """

    final_response = llm.invoke(prompt).content
    return {
        "final_response": final_response,
        "messages": [AIMessage(content=final_response)]
    }


Graph = StateGraph(AgentSchema)

# Now we have the nodes -- now just add the edges --
Graph.add_node("curateQuery",curateQuery)
Graph.add_node("prompt_with_sqlContext",prompt_with_sqlContext)
Graph.add_node("generated_sql_query",generated_sql_query)
Graph.add_node("safe_node_sql",safe_node_sql)
Graph.add_node("safeNode_sql_exit",safeNode_sql_exit)
Graph.add_node("safeNdoe_sql_execute",safeNdoe_sql_execute)
Graph.add_node("final_answer_node",final_answer_node)


Graph.add_edge(START,"curateQuery")
Graph.add_edge("curateQuery","prompt_with_sqlContext")
Graph.add_edge("prompt_with_sqlContext","generated_sql_query")
Graph.add_edge("generated_sql_query","safe_node_sql")

# create teh conditional edge fucntion--
def is_safe_edge(state: AgentSchema) -> str:
    safe = state.is_safe
    if safe == "YES":
        return "safeNdoe_sql_execute"
    else:
        return "safeNode_sql_exit"
Graph.add_conditional_edges('safe_node_sql',is_safe_edge,) # here we pass like this (to make the conditonal edges) .

# we can aslso do like this -- graph.add_conditional_edges('safe_node_sql', is_safe_edge, { "YES": "safeNdoe_sql_execute",
#    "NO":  "safeNode_sql_exit"
# })
Graph.add_edge("safeNode_sql_exit",END) # Means agar ab conditional me cancel aata ha too ye execute hooga .
Graph.add_edge("safeNdoe_sql_execute","final_answer_node") # or coditional edge pr ye aata ha too ye execute hooga .
Graph.add_edge("final_answer_node",END)


# Compile --
Workflow = Graph.compile()


user_input = input("Enter your query : ")
final_responses = Workflow.invoke({ # need o send all because er make filed must need with this (...)
    "user_question":user_input,
    "messages":[],
    "curated_question":"",
    "prompt_context":"",
    "ai_generated_sqlQuery":"",
    "is_safe":"NO",
    "comments":"",
    "sql_result":"",
    "final_response":""
})

print("**********************")
print(final_responses['messages'])
print("**********************")
print(final_responses['sql_result'])
print("**********************")
print(final_responses['is_safe'])
print("**********************")
print(final_responses['ai_generated_sqlQuery'])
print("**********************")
print(final_responses['final_response'])    