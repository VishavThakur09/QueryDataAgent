import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from utils.etl_tools import ETLTOOLS
from utils.modelPick import model_pick
from models.schema import etl_structure_schema

load_dotenv()

# ============================================================================
# 1. INITIALIZE ETL UTILITIES & DEFINE TOOLS
# ============================================================================

etl = ETLTOOLS()

@tool
def extract_api_data(url: str, output_folder: str = "data/raw") -> str:
    """Extracts raw JSON data from an API URL and saves it to the output folder."""
    return etl.extract_load(url=url, output_folder=output_folder)

@tool
def transform_raw_data(input_file: str, output_file: str = None) -> str:
    """Transforms raw JSON data into a clean, tabular CSV file for database loading."""
    return etl.transform_data(input_file=input_file, output_file=output_file)

@tool
def load_data_to_database(input_file: str, table_name: str) -> str:
    """Loads a transformed CSV or JSON file into a PostgreSQL database table."""
    return etl.execute_load(input_file=input_file, table_name=table_name)

@tool
def execute_sql_query(query: str) -> str:
    """Executes a SQL query against the database to inspect or verify loaded data."""
    return etl.execute_query(query=query)

# List of all tools available to the agent
tools = [extract_api_data, transform_raw_data, load_data_to_database, execute_sql_query]


# ============================================================================
# 2. BIND TOOLS WITH HIGH-TIER LLM
# ============================================================================

llm = model_pick("high")
llm_with_tools = llm.bind_tools(tools)


# ============================================================================
# 3. AGENT NODE
# ============================================================================

SYSTEM_PROMPT = SystemMessage(
    content="""You are an expert ETL (Extract, Transform, Load) Analyst Agent.
Your job is to manage data pipelines using your available tools:
1. extract_api_data: Download raw data from an API to 'data/raw/<name>.json'.
2. transform_raw_data: Clean and flatten raw JSON into 'data/processed/<name>.csv'.
3. load_data_to_database: Insert processed CSV data into a PostgreSQL table.
4. execute_sql_query: Inspect and verify table contents after loading.

Always inspect the user's request and use the appropriate tool step by step.
When the entire ETL process is complete, summarize what was done in plain English."""
)

def etl_agent_node(state: etl_structure_schema) -> dict:
    """Agent node that inspects current conversation and decides whether to call a tool or reply."""
    messages = state.messages
    # Prepend system prompt if not present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SYSTEM_PROMPT] + messages

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# ============================================================================
# 4. BUILD LANGGRAPH WORKFLOW
# ============================================================================

workflow = StateGraph(etl_structure_schema)

# Add agent and tool execution nodes
workflow.add_node("agent", etl_agent_node)
workflow.add_node("tools", ToolNode(tools))

# Connect START to the agent
workflow.add_edge(START, "agent")

# If agent decided to call tools -> route to 'tools', else -> route to END
workflow.add_conditional_edges("agent", tools_condition)

# After tools execute, pass results back to agent to review or summarize
workflow.add_edge("tools", "agent")

# Compile graph
etl_app = workflow.compile()


# ============================================================================
# 5. TESTING / EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("\n--- ETL Analyst Agent Ready ---")
    user_input = input("Enter your ETL instruction: ")
    
    initial_state = {
        "messages": [HumanMessage(content=user_input)]
    }
    
    # Run the graph
    result = etl_app.invoke(initial_state)
    
    print("\n================ FINAL RESPONSE ================")
    print(result["messages"][-1].content)



# *********** I.N ***************
# HOW can run give the instruction int h termial like ----  Extract pokemon data from https://pokeapi.co/api/v2/pokemon?limit=151, transform it into CSV, and load it into a table called pokemon_characters.
