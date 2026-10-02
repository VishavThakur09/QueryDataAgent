import psycopg2

class DatabaseUtils:
    def __init__(self, db_config):
        self.db_config = db_config
        try:
            self.connection = psycopg2.connect(**db_config)
            self.cursor = self.connection.cursor()
            print("Database Connected Successfully")
        except Exception as e:
            print(f"Error connecting to the database: {e}")

    def schema_details(self, schema_name):
        try:
            connection = psycopg2.connect(**self.db_config)
            cursor = connection.cursor()

            schema_info = f"The database schema: {schema_name}\n"

            # FETCH THE TABLES
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", (schema_name,))
            tables = cursor.fetchall()

            for table in tables:
                table_name = table[0]
                schema_info += f"\nTable: {table_name}\n"

                # FETCH COLUMNS (just names and types — no repetition)
                cursor.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s", (table_name,))
                columns = cursor.fetchall()
                schema_info += "    Columns:\n"
                for col in columns:
                    schema_info += f"      - {col[0]} ({col[1]})\n"

                # FETCH SAMPLE ROWS ONCE per table (not once per column)
                cursor.execute(f"SELECT * FROM {schema_name}.{table_name} LIMIT 3")
                rows = cursor.fetchall()
                col_names = [desc[0] for desc in cursor.description]
                schema_info += f"    Sample rows ({', '.join(col_names)}):\n"
                for row in rows:
                    schema_info += f"      {row}\n"

        except Exception as e:
            print(f"Error fetching schema details: {e}")
            return None
        finally:
            cursor.close()
            connection.close()

        return schema_info

    def execute_query(self, query: str) -> str:
        try:
            connection = psycopg2.connect(**self.db_config)
            cursor = connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            return str(rows)
        except Exception as e:
            print(f"Error executing query: {e}")
            return None
        finally:
            cursor.close()
            connection.close()