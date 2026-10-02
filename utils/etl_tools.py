import os
import re
import csv
import json
import requests
import psycopg2
from psycopg2 import extras
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

class ETLTOOLS:

    def __init__(self, db_config: dict = None):
        """
        Initializes ETLTOOLS with optional database configuration.
        Falls back to environment variables if db_config is not provided.
        """
        self.db_config = db_config or {
            "host": os.getenv("host"),
            "user": os.getenv("user"),
            "password": os.getenv("passward") or os.getenv("password"),
            "dbname": os.getenv("database"),
            "port": os.getenv("port", "5432"),
        }

    # 1. EXTRACT TOOL
    def extract_load(self, url: str, output_folder: str = "data/raw") -> str:
        """
        Extracts raw data from the given API URL and saves it as a JSON file in the output folder.
        
        Args:
            url (str): The API endpoint URL.
            output_folder (str): Directory where the downloaded file should be saved.
            
        Returns:
            str: Status message indicating success with file path or reason for failure.
        """
        clean_url = url.strip().rstrip("'\"")
        
        try:
            response = requests.get(clean_url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            os.makedirs(output_folder, exist_ok=True)
            
            parsed_path = urlparse(clean_url).path.strip("/").split("/")
            endpoint_name = parsed_path[-1] if parsed_path and parsed_path[-1] else "api_data"
            file_path = os.path.join(output_folder, f"{endpoint_name}.json")
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
            record_count = len(data.get("results", data if isinstance(data, list) else [data]))
            return f"Success: Extracted {record_count} records from {clean_url} and saved to {file_path}"

        except requests.exceptions.Timeout:
            return f"Failure: Request timed out while connecting to {clean_url}"
        except requests.exceptions.HTTPError as http_err:
            return f"Failure: HTTP error occurred ({response.status_code}): {http_err}"
        except requests.exceptions.RequestException as req_err:
            return f"Failure: Network/Connection error occurred: {req_err}"
        except json.JSONDecodeError:
            return f"Failure: Response from {clean_url} is not valid JSON."
        except Exception as e:
            return f"Failure: An unexpected error occurred: {str(e)}"

    # 2. TRANSFORM TOOL
    def transform_data(self, input_file: str, output_file: str = None) -> str:
        """
        Transforms raw JSON data into clean, flattened tabular records and saves as CSV.
        Handles extracting nested arrays (e.g. 'results' or 'data'), cleaning fields,
        and extracting IDs from URLs when present.
        
        Args:
            input_file (str): Path to the raw JSON file.
            output_file (str, optional): Target CSV path (defaults to data/processed/<filename>.csv).
            
        Returns:
            str: Status message indicating success with output file path or reason for failure.
        """
        try:
            if not os.path.exists(input_file):
                return f"Failure: Input file '{input_file}' does not exist."

            with open(input_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            # Determine records list
            records = []
            if isinstance(raw_data, list):
                records = raw_data
            elif isinstance(raw_data, dict):
                # Check common wrapper keys: 'results', 'data', 'items'
                for key in ["results", "data", "items", "records"]:
                    if key in raw_data and isinstance(raw_data[key], list):
                        records = raw_data[key]
                        break
                if not records:
                    # Single object dict -> treat as single row
                    records = [raw_data]

            if not records:
                return f"Failure: No records found to transform in {input_file}"

            # Flatten and clean each record
            flattened_records = []
            for item in records:
                if not isinstance(item, dict):
                    continue
                row = {}
                for k, v in item.items():
                    # If value is simple dict/list, serialize or extract
                    if isinstance(v, (dict, list)):
                        row[k] = json.dumps(v)
                    else:
                        row[k] = str(v).strip() if v is not None else ""

                # Special check: Extract ID if URL has pattern like /pokemon/25/
                if "url" in row and ("id" not in row or not row["id"]):
                    match = re.search(r"/(\d+)/?$", row["url"])
                    if match:
                        row["id"] = int(match.group(1))

                flattened_records.append(row)

            if not flattened_records:
                return f"Failure: Could not parse any valid rows from {input_file}"

            # Auto-assign output path if not specified
            if not output_file:
                base_name = os.path.splitext(os.path.basename(input_file))[0]
                output_folder = "data/processed"
                os.makedirs(output_folder, exist_ok=True)
                output_file = os.path.join(output_folder, f"{base_name}.csv")
            else:
                os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

            # Gather unified column headers
            fieldnames = []
            # Place 'id' first if present
            all_keys = set().union(*(d.keys() for d in flattened_records))
            if "id" in all_keys:
                fieldnames.append("id")
            for k in sorted(all_keys):
                if k not in fieldnames:
                    fieldnames.append(k)

            # Write clean CSV
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(flattened_records)

            return f"Success: Transformed {len(flattened_records)} records and saved to {output_file}"

        except Exception as e:
            return f"Failure: Transformation error occurred: {str(e)}"

    # 3. EXECUTE / LOAD TOOL
    def execute_load(self, input_file: str, table_name: str, db_config: dict = None) -> str:
        """
        Executes loading of transformed CSV or JSON data into a PostgreSQL database table.
        Automatically creates the table if it does not already exist.
        
        Args:
            input_file (str): Path to the processed CSV or JSON file.
            table_name (str): Target database table name.
            db_config (dict, optional): Custom database connection parameters.
            
        Returns:
            str: Status message indicating success or failure.
        """
        config = db_config or self.db_config
        if not config or not config.get("host"):
            return "Failure: Missing database configuration credentials."

        if not os.path.exists(input_file):
            return f"Failure: Input file '{input_file}' does not exist."

        # Read records from CSV or JSON
        records = []
        try:
            if input_file.endswith(".csv"):
                with open(input_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    records = list(reader)
            elif input_file.endswith(".json"):
                with open(input_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = data if isinstance(data, list) else [data]
            else:
                return f"Failure: Unsupported file format '{input_file}'. Please provide .csv or .json"
        except Exception as e:
            return f"Failure reading input file: {str(e)}"

        if not records:
            return f"Failure: No records to load from '{input_file}'."

        columns = list(records[0].keys())
        # Clean table & column names to prevent SQL injection
        safe_table_name = re.sub(r"[^a-zA-Z0-9_]", "", table_name)
        safe_columns = [re.sub(r"[^a-zA-Z0-9_]", "", col) for col in columns]

        # Prepare database connection
        connection = None
        cursor = None
        try:
            connection = psycopg2.connect(**config)
            cursor = connection.cursor()

            # Create table if not exists with appropriate column definitions
            col_definitions = [f'"{col}" TEXT' for col in safe_columns]
            create_table_sql = f'CREATE TABLE IF NOT EXISTS "{safe_table_name}" ({", ".join(col_definitions)});'
            cursor.execute(create_table_sql)

            # Insert rows using execute_batch
            col_names_str = ", ".join([f'"{col}"' for col in safe_columns])
            placeholders = ", ".join(["%s"] * len(safe_columns))
            insert_sql = f'INSERT INTO "{safe_table_name}" ({col_names_str}) VALUES ({placeholders})'

            data_tuples = [
                tuple(row.get(col, None) for col in columns)
                for row in records
            ]

            extras.execute_batch(cursor, insert_sql, data_tuples)
            connection.commit()

            return f"Success: Loaded {len(data_tuples)} records into database table '{safe_table_name}'."

        except psycopg2.Error as pg_err:
            if connection:
                connection.rollback()
            return f"Failure: PostgreSQL database error: {pg_err}"
        except Exception as e:
            if connection:
                connection.rollback()
            return f"Failure: Unexpected error during load execution: {str(e)}"
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    # 4. EXECUTE QUERY TOOL (Helper to verify or run queries on DB)
    def execute_query(self, query: str, db_config: dict = None) -> str:
        """
        Executes a SQL query against the database and returns the result as string.
        
        Args:
            query (str): SQL query to execute.
            db_config (dict, optional): Custom DB config if different from default.
            
        Returns:
            str: Query output or error message.
        """
        config = db_config or self.db_config
        connection = None
        cursor = None
        try:
            connection = psycopg2.connect(**config)
            cursor = connection.cursor()
            cursor.execute(query)
            
            # If query returns rows (e.g. SELECT)
            if cursor.description:
                rows = cursor.fetchall()
                col_names = [desc[0] for desc in cursor.description]
                return f"Columns: {col_names}\nRows ({len(rows)}):\n" + "\n".join(str(r) for r in rows[:20])
            else:
                connection.commit()
                return f"Success: Query executed successfully (affected {cursor.rowcount} rows)."
                
        except Exception as e:
            if connection:
                connection.rollback()
            return f"Failure executing query: {str(e)}"
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
