# database.py (с исправлением обработки параметров)
import os
import psycopg2
import subprocess
from psycopg2.extras import RealDictCursor, DictCursor
from dotenv import load_dotenv
from datetime import datetime
import json
import pandas as pd
import shutil
from pathlib import Path
import csv

load_dotenv()

class DBManager:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'postgres'),
            'database': os.getenv('DB_NAME', 'my_app_db'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres'),
            'port': os.getenv('DB_PORT', '5432')
        }
        self.pg_dump_path = "pg_dump"
        self.pg_restore_path = "pg_restore"
        
        self.folders = self.setup_folders()
    
    def setup_folders(self):
        base_folders = {
            'backups': Path("/app/backups"),
            'exports': Path("/app/exports"),
            'archives': Path("/app/archives")
        }
        
        for folder in base_folders.values():
            folder.mkdir(exist_ok=True, parents=True)
        
        return base_folders
    
    def create_folder_with_time(self, base_folder):
        time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_folder = base_folder / time_str
        new_folder.mkdir(parents=True, exist_ok=True)
        return new_folder
    
    def get_db_connection(self, dict_mode=True):
        try:
            conn = psycopg2.connect(
                **self.db_config,
                cursor_factory=RealDictCursor if dict_mode else DictCursor
            )
            return conn
        except Exception as e:
            print(f"Connection error: {e}")
            return None
    
    def run_sql(self, sql, params=None, fetch=True):
        conn = self.get_db_connection()
        if not conn:
            return None
        
        try:
            with conn.cursor() as cursor:
                # Преобразуем параметры для psycopg2
                sql_params = self._prepare_params(params)
                
                if sql_params:
                    cursor.execute(sql, sql_params)
                else:
                    cursor.execute(sql)
                    
                if fetch and cursor.description:
                    result = cursor.fetchall()
                else:
                    result = None
                conn.commit()
                return result
        except Exception as e:
            conn.rollback()
            print(f"SQL execution error: {e}")
            return None
        finally:
            conn.close()
    
    def _prepare_params(self, params):
        """Преобразует параметры из JSON формата в формат, понятный psycopg2"""
        if not params:
            return None
        
        try:
            if isinstance(params, dict):
                # Если это словарь с числовыми ключами (0, 1, 2...)
                if all(str(k).isdigit() for k in params.keys() if k is not None):
                    # Сортируем по ключам и возвращаем список значений
                    sorted_keys = sorted([int(k) for k in params.keys() if str(k).isdigit()])
                    return tuple(params[str(k)] for k in sorted_keys)
                else:
                    # Для именованных параметров просто возвращаем словарь
                    return params
            elif isinstance(params, list):
                # Если это список - возвращаем как кортеж
                return tuple(params)
            else:
                # Если это строка JSON
                if isinstance(params, str):
                    parsed = json.loads(params)
                    return self._prepare_params(parsed)
                return params
        except Exception as e:
            print(f"Error preparing params: {e}")
            # Возвращаем как есть, если не удалось обработать
            if isinstance(params, dict):
                return params
            elif isinstance(params, list):
                return tuple(params)
            return params
    
    def get_all_tables(self):
        sql = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """
        result = self.run_sql(sql)
        return [row['table_name'] for row in result] if result else []
    
    def get_table_info(self, table_name):
        sql = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """
        return self.run_sql(sql, (table_name,))
    
    def get_table_pk(self, table_name):
        sql = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = %s 
            AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """
        result = self.run_sql(sql, (table_name,))
        if result and len(result) > 0:
            return result[0]['column_name']
        return None
    
    def get_table_links(self, table_name):
        sql = """
            SELECT
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            LEFT JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_name = %s
            AND tc.constraint_type IN ('FOREIGN KEY', 'PRIMARY KEY')
            ORDER BY tc.constraint_type, kcu.ordinal_position;
        """
        return self.run_sql(sql, (table_name,))
    
    def get_related_tables(self, table_name, column_name=None):
        sql = """
            SELECT
                tc.table_name as referencing_table,
                kcu.column_name as referencing_column,
                ccu.table_name as referenced_table,
                ccu.column_name as referenced_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND ccu.table_name = %s
            AND (%s IS NULL OR ccu.column_name = %s)
        """
        return self.run_sql(sql, (table_name, column_name, column_name))
    
    def get_table_rows(self, table_name, limit=None, offset=0):
        try:
            if limit:
                sql = f'SELECT * FROM "{table_name}" LIMIT %s OFFSET %s'
                return self.run_sql(sql, (limit, offset))
            else:
                sql = f'SELECT * FROM "{table_name}"'
                return self.run_sql(sql)
        except Exception as e:
            print(f"Error getting data from {table_name}: {e}")
            return []
    
    def get_row_count(self, table_name):
        try:
            sql = f'SELECT COUNT(*) as count FROM "{table_name}"'
            result = self.run_sql(sql)
            return result[0]['count'] if result else 0
        except Exception as e:
            print(f"Error counting rows in {table_name}: {e}")
            return 0
    
    def add_row(self, table_name, data):
        try:
            # Удаляем пустые значения для не-nullable полей
            columns_info = self.get_table_info(table_name)
            if not columns_info:
                return None
            
            nullable_columns = [col['column_name'] for col in columns_info if col['is_nullable'] == 'YES']
            filtered_data = {}
            
            for key, value in data.items():
                if value is not None and value != '':
                    filtered_data[key] = value
                elif key in nullable_columns:
                    filtered_data[key] = None
                # Если поле не nullable и значение пустое - пропускаем
            
            if not filtered_data:
                return None
                
            columns = ', '.join([f'"{col}"' for col in filtered_data.keys()])
            placeholders = ', '.join(['%s'] * len(filtered_data))
            
            pk = self.get_table_pk(table_name)
            if pk:
                sql = f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders}) RETURNING "{pk}"'
            else:
                sql = f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})'
            
            conn = self.get_db_connection()
            if not conn:
                return None
            
            cursor = conn.cursor()
            cursor.execute(sql, tuple(filtered_data.values()))
            
            if pk:
                result = cursor.fetchone()
                inserted_id = result[pk] if result else None
            else:
                inserted_id = None
            
            conn.commit()
            conn.close()
            
            return inserted_id
        except Exception as e:
            print(f"Error adding data to {table_name}: {e}")
            return None
    
    def modify_row(self, table_name, data, condition):
        try:
            if not condition or condition.strip() == "":
                return {"ok": False, "msg": "Condition cannot be empty"}
            
            # Получаем информацию о nullable полях
            columns_info = self.get_table_info(table_name)
            nullable_columns = [col['column_name'] for col in columns_info] if columns_info else []
            
            # Обрабатываем данные
            clean_data = {}
            for key, value in data.items():
                if value is not None and value != '':
                    clean_data[key] = value
                elif key in nullable_columns:
                    clean_data[key] = None
            
            if not clean_data:
                return {"ok": False, "msg": "No data to update"}
            
            set_parts = []
            values = []
            
            for key, value in clean_data.items():
                set_parts.append(f'"{key}" = %s')
                values.append(value)
            
            set_clause = ', '.join(set_parts)
            sql = f'UPDATE "{table_name}" SET {set_clause} WHERE {condition}'
            
            conn = self.get_db_connection()
            if not conn:
                return {"ok": False, "msg": "Cannot connect to DB"}
            
            cursor = conn.cursor()
            cursor.execute(sql, tuple(values))
            changed = cursor.rowcount
            conn.commit()
            conn.close()
            
            return {
                "ok": True,
                "changed": changed,
                "msg": f"Updated {changed} records"
            }
            
        except Exception as e:
            print(f"Error updating data in {table_name}: {e}")
            return {"ok": False, "msg": str(e)}
    
    def remove_row(self, table_name, condition, cascade=False):
        try:
            if not condition or condition.strip() == "":
                return {"ok": False, "msg": "Condition cannot be empty"}
            
            conn = self.get_db_connection()
            if not conn:
                return {"ok": False, "msg": "Cannot connect to DB"}
            
            cursor = conn.cursor()
            
            if cascade:
                related_tables = self.get_related_tables(table_name)
                
                for rel_table in related_tables:
                    rel_name = rel_table['referencing_table']
                    rel_column = rel_table['referencing_column']
                    
                    pk = self.get_table_pk(table_name)
                    if not pk:
                        subquery = f'SELECT "{rel_column}" FROM "{table_name}" WHERE {condition}'
                        delete_sql = f'DELETE FROM "{rel_name}" WHERE "{rel_column}" IN ({subquery})'
                    else:
                        subquery = f'SELECT "{pk}" FROM "{table_name}" WHERE {condition}'
                        delete_sql = f'DELETE FROM "{rel_name}" WHERE "{rel_column}" IN ({subquery})'
                    
                    cursor.execute(delete_sql)
            
            delete_sql = f'DELETE FROM "{table_name}" WHERE {condition}'
            cursor.execute(delete_sql)
            
            changed = cursor.rowcount
            conn.commit()
            conn.close()
            
            return {
                "ok": True,
                "changed": changed,
                "msg": f"Removed {changed} records"
            }
            
        except Exception as e:
            print(f"Error deleting from {table_name}: {e}")
            return {"ok": False, "msg": str(e)}
    
    def safe_remove(self, table_name, condition):
        try:
            if not condition or condition.strip() == "":
                return {"ok": False, "msg": "Condition cannot be empty"}
            
            conn = self.get_db_connection()
            if not conn:
                return {"ok": False, "msg": "Cannot connect to DB"}
            
            cursor = conn.cursor()
            
            related_tables = self.get_related_tables(table_name)
            
            has_relations = False
            relation_info = []
            
            for rel_table in related_tables:
                rel_name = rel_table['referencing_table']
                rel_column = rel_table['referencing_column']
                
                pk = self.get_table_pk(table_name)
                if pk:
                    subquery = f'SELECT "{pk}" FROM "{table_name}" WHERE {condition}'
                    check_sql = f'SELECT COUNT(*) FROM "{rel_name}" WHERE "{rel_column}" IN ({subquery})'
                else:
                    subquery = f'SELECT "{rel_column}" FROM "{table_name}" WHERE {condition}'
                    check_sql = f'SELECT COUNT(*) FROM "{rel_name}" WHERE "{rel_column}" IN ({subquery})'
                
                cursor.execute(check_sql)
                count = cursor.fetchone()[0]
                
                if count > 0:
                    has_relations = True
                    relation_info.append({
                        'table': rel_name,
                        'column': rel_column,
                        'count': count
                    })
            
            if has_relations:
                conn.close()
                return {
                    'ok': False,
                    'msg': 'Found related records',
                    'has_relations': True,
                    'relations': relation_info
                }
            
            delete_sql = f'DELETE FROM "{table_name}" WHERE {condition}'
            cursor.execute(delete_sql)
            
            changed = cursor.rowcount
            conn.commit()
            conn.close()
            
            return {
                'ok': True,
                'changed': changed,
                'msg': f'Removed {changed} records'
            }
            
        except Exception as e:
            print(f"Error in safe remove: {e}")
            return {
                'ok': False,
                'msg': str(e)
            }
    
    def drop_table_completely(self, table_name):
        try:
            sql = f'DROP TABLE IF EXISTS "{table_name}" CASCADE'
            conn = self.get_db_connection(dict_mode=False)
            if not conn:
                return False
            
            try:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    conn.commit()
                    return True
            except Exception as e:
                conn.rollback()
                print(f"Error dropping table {table_name}: {e}")
                return False
            finally:
                conn.close()
        except Exception as e:
            print(f"Exception dropping table {table_name}: {e}")
            return False
    
    def table_present(self, table_name):
        try:
            sql = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                )
            """
            result = self.run_sql(sql, (table_name,))
            return result[0]['exists'] if result else False
        except Exception as e:
            print(f"Error checking table {table_name}: {e}")
            return False
    
    def wipe_database(self):
        try:
            conn = self.get_db_connection(dict_mode=False)
            if not conn:
                return False, "DB connection error"
            
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY tablename
            """)
            tables = cursor.fetchall()
            
            if not tables:
                conn.close()
                return True, "No tables found"
            
            table_names = [table[0] for table in tables]
            removed = 0
            
            for name in table_names:
                try:
                    cursor.execute(f'DROP TABLE IF EXISTS "{name}" CASCADE')
                    removed += 1
                    
                except Exception as e:
                    print(f"Error dropping table {name}: {e}")
                    conn.rollback()
                    conn.close()
                    return False, f"Failed to drop {name}: {str(e)}"
            
            conn.commit()
            conn.close()
            
            return True, f"Dropped {removed} tables"
            
        except Exception as e:
            print(f"Exception wiping database: {e}")
            return False, f"Error: {str(e)}"
    
    def save_table_to_xlsx(self, table_name):
        try:
            data = self.get_table_rows(table_name, limit=50000)
            if not data:
                return None, "No data to save"
            
            save_dir = self.create_folder_with_time(self.folders['exports'])
            filename = f"{table_name}_{datetime.now().strftime('%H%M%S')}.xlsx"
            filepath = save_dir / filename
            
            df = pd.DataFrame(data)
            df.to_excel(str(filepath), index=False)
            
            return str(filepath), filename
            
        except Exception as e:
            return None, str(e)
    
    def save_table_to_json(self, table_name):
        try:
            data = self.get_table_rows(table_name, limit=50000)
            if not data:
                return None, "No data to save"
            
            save_dir = self.create_folder_with_time(self.folders['exports'])
            filename = f"{table_name}_{datetime.now().strftime('%H%M%S')}.json"
            filepath = save_dir / filename
            
            json_data = []
            for row in data:
                json_row = {}
                for key, value in row.items():
                    if isinstance(value, (datetime, pd.Timestamp)):
                        json_row[key] = value.isoformat()
                    elif hasattr(value, '__dict__'):
                        json_row[key] = str(value)
                    else:
                        json_row[key] = value
                json_data.append(json_row)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
            
            return str(filepath), filename
            
        except Exception as e:
            return None, str(e)
    
    def save_query_to_xlsx(self, result_data, query_name="result"):
        try:
            if not result_data:
                return None, "No data to save"
            
            temp_table = f"temp_export_{datetime.now().strftime('%H%M%S')}"
            
            conn = self.get_db_connection(dict_mode=False)
            if not conn:
                return None, "Connection error"
            
            try:
                with conn.cursor() as cursor:
                    first_row = result_data[0]
                    columns = list(first_row.keys())
                    
                    column_defs = []
                    for col in columns:
                        column_defs.append(f'"{col}" TEXT')
                    
                    create_sql = f"""
                        CREATE TEMPORARY TABLE {temp_table} (
                            {', '.join(column_defs)}
                        )
                    """
                    cursor.execute(create_sql)
                    
                    for row in result_data:
                        placeholders = ', '.join(['%s'] * len(columns))
                        insert_sql = f"""
                            INSERT INTO {temp_table} ({', '.join([f'"{c}"' for c in columns])})
                            VALUES ({placeholders})
                        """
                        values = [str(row.get(col, '')) for col in columns]
                        cursor.execute(insert_sql, values)
                    
                    conn.commit()
                    
                    save_dir = self.create_folder_with_time(self.folders['exports'])
                    filename = f"{query_name}_{datetime.now().strftime('%H%M%S')}.xlsx"
                    filepath = save_dir / filename
                    
                    cursor.execute(f'SELECT * FROM {temp_table}')
                    rows = cursor.fetchall()
                    column_names = [desc[0] for desc in cursor.description]
                    
                    df = pd.DataFrame(rows, columns=column_names)
                    df.to_excel(str(filepath), index=False)
                    
                    cursor.execute(f'DROP TABLE IF EXISTS {temp_table}')
                    conn.commit()
                    
                    return str(filepath), filename
                    
            except Exception as e:
                conn.rollback()
                return None, f"Error: {str(e)}"
            finally:
                conn.close()
                
        except Exception as e:
            return None, str(e)
    
    def save_query_to_csv(self, result_data):
        try:
            if not result_data:
                return None, "No data to save"
            
            return self.save_query_to_xlsx(result_data, "query_result")
            
        except Exception as e:
            return None, str(e)
    
    def create_database_backup(self):
        try:
            db_name = os.getenv('DB_NAME', 'my_app_db')
            db_user = os.getenv('DB_USER', 'postgres')
            db_host = os.getenv('DB_HOST', 'postgres')
            db_port = os.getenv('DB_PORT', '5432')
            
            save_dir = self.create_folder_with_time(self.folders['backups'])
            time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = save_dir / f"backup_{db_name}_{time_str}.backup"
            
            cmd = [
                self.pg_dump_path,
                '-h', db_host,
                '-U', db_user,
                '-p', db_port,
                '-d', db_name,
                '-F', 'c',
                '--no-tablespaces',
                '--no-unlogged-table-data',
                '-f', str(backup_file),
                '-v'
            ]
            
            env = os.environ.copy()
            env['PGPASSWORD'] = os.getenv('DB_PASSWORD', 'postgres')
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                shell=False
            )
            
            if result.returncode == 0:
                return True, str(backup_file), None
            else:
                error_msg = f"pg_dump error:\n{result.stderr}\n{result.stdout}"
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Backup exception: {str(e)}"
            return False, None, error_msg
    
    def create_single_table_backup(self, table_name, save_dir):
        try:
            db_user = os.getenv('DB_USER', 'postgres')
            db_host = os.getenv('DB_HOST', 'postgres')
            db_port = os.getenv('DB_PORT', '5432')
            db_name = os.getenv('DB_NAME', 'my_app_db')
            
            backup_file = save_dir / f"backup_{table_name}_{datetime.now().strftime('%H%M%S')}.backup"
            
            cmd = [
                self.pg_dump_path,
                '-h', db_host,
                '-U', db_user,
                '-p', db_port,
                '-d', db_name,
                '-t', table_name,
                '-F', 'c',
                '--no-tablespaces',
                '--no-unlogged-table-data',
                '-f', str(backup_file),
                '-v'
            ]
            
            env = os.environ.copy()
            env['PGPASSWORD'] = os.getenv('DB_PASSWORD', 'postgres')
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                shell=False
            )
            
            if result.returncode == 0:
                return True, str(backup_file), None
            else:
                error_msg = f"pg_dump error for {table_name}:\n{result.stderr}\n{result.stdout}"
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Table backup exception for {table_name}: {str(e)}"
            return False, None, error_msg
    
    def restore_from_backup(self, backup_file):
        try:
            if not os.path.exists(backup_file):
                return False, f"File not found: {backup_file}"
            
            db_user = os.getenv('DB_USER', 'postgres')
            db_host = os.getenv('DB_HOST', 'postgres')
            db_port = os.getenv('DB_PORT', '5432')
            db_name = os.getenv('DB_NAME', 'my_app_db')
            
            try:
                conn = psycopg2.connect(**self.db_config)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                """)
                tables = cursor.fetchall()
                
                for table in tables:
                    cursor.execute(f'DROP TABLE IF EXISTS "{table[0]}" CASCADE')
                
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error dropping tables: {e}")
            
            cmd = [
                self.pg_restore_path,
                '-h', db_host,
                '-U', db_user,
                '-p', db_port,
                '-d', db_name,
                '-v',
                '--clean',
                '--if-exists',
                '--no-comments',
                '--no-tablespaces',
                str(backup_file)
            ]
            
            env = os.environ.copy()
            env['PGPASSWORD'] = os.getenv('DB_PASSWORD', 'postgres')
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                shell=False
            )
            
            output = result.stdout + result.stderr
            
            if "unrecognized configuration parameter \"transaction_timeout\"" in output:
                print("Warning: transaction_timeout error ignored")
                return True, "Restored (some warnings ignored)"
            
            if result.returncode == 0:
                return True, "Restore successful"
            else:
                error_msg = f"pg_restore error:\n{result.stderr}\n{result.stdout}"
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Restore exception: {str(e)}"
            return False, error_msg
    
    def save_tables_to_xlsx(self, table_names):
        try:
            if not table_names:
                return None, "No tables selected"
            
            valid_tables = []
            for table in table_names:
                if self.table_present(table):
                    valid_tables.append(table)
            
            if not valid_tables:
                return None, "No valid tables found"
            
            save_dir = self.create_folder_with_time(self.folders['exports'])
            filename = f"export_{datetime.now().strftime('%H%M%S')}.xlsx"
            filepath = save_dir / filename
            
            with pd.ExcelWriter(str(filepath), engine='openpyxl') as writer:
                for table in valid_tables:
                    data = self.get_table_rows(table, limit=50000)
                    if data:
                        df = pd.DataFrame(data)
                        sheet_name = table[:31]
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            return str(filepath), filename
            
        except Exception as e:
            return None, str(e)
    
    def save_tables_to_json(self, table_names):
        try:
            if not table_names:
                return None, "No tables selected"
            
            valid_tables = []
            for table in table_names:
                if self.table_present(table):
                    valid_tables.append(table)
            
            if not valid_tables:
                return None, "No valid tables found"
            
            save_dir = self.create_folder_with_time(self.folders['exports'])
            filename = f"export_{datetime.now().strftime('%H%M%S')}.json"
            filepath = save_dir / filename
            
            result = {}
            for table in valid_tables:
                data = self.get_table_rows(table, limit=50000)
                if data:
                    json_data = []
                    for row in data:
                        json_row = {}
                        for key, value in row.items():
                            if isinstance(value, (datetime, pd.Timestamp)):
                                json_row[key] = value.isoformat()
                            elif hasattr(value, '__dict__'):
                                json_row[key] = str(value)
                            else:
                                json_row[key] = value
                        json_data.append(json_row)
                    result[table] = json_data
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
            
            return str(filepath), filename
            
        except Exception as e:
            return None, str(e)
    
    def save_all_to_xlsx(self):
        tables = self.get_all_tables()
        return self.save_tables_to_xlsx(tables)
    
    def save_all_to_json(self):
        tables = self.get_all_tables()
        return self.save_tables_to_json(tables)
    
    def pack_tables(self, table_names):
        try:
            if not table_names:
                return False, "No tables selected"
            
            valid_tables = []
            for table in table_names:
                if self.table_present(table):
                    valid_tables.append(table)
            
            if not valid_tables:
                return False, "No valid tables found"
            
            archive_dir = self.create_folder_with_time(self.folders['archives'])
            
            results = []
            all_good = True
            
            for table in valid_tables:
                try:
                    backup_ok, backup_file, backup_error = self.create_single_table_backup(table, archive_dir)
                    
                    if not backup_ok:
                        results.append(f"Backup error for '{table}': {backup_error}")
                        all_good = False
                        continue
                    
                    excel_filename = f"{table}_{datetime.now().strftime('%H%M%S')}.xlsx"
                    excel_path = archive_dir / excel_filename
                    
                    data = self.get_table_rows(table)
                    row_count = len(data) if data else 0
                    
                    if data:
                        df = pd.DataFrame(data)
                        df.to_excel(str(excel_path), index=False)
                    
                    json_filename = f"{table}_{datetime.now().strftime('%H%M%S')}.json"
                    json_path = archive_dir / json_filename
                    
                    json_data = []
                    if data:
                        for row in data:
                            json_row = {}
                            for key, value in row.items():
                                if isinstance(value, (datetime, pd.Timestamp)):
                                    json_row[key] = value.isoformat()
                                elif hasattr(value, '__dict__'):
                                    json_row[key] = str(value)
                                else:
                                    json_row[key] = value
                            json_data.append(json_row)
                    
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
                    
                    drop_ok = self.drop_table_completely(table)
                    
                    if drop_ok:
                        results.append({
                            'table': table,
                            'backup_file': os.path.basename(backup_file),
                            'excel_file': excel_filename,
                            'json_file': json_filename,
                            'rows': row_count,
                            'status': 'ok'
                        })
                    else:
                        results.append(f"Error dropping table '{table}'")
                        all_good = False
                    
                except Exception as e:
                    results.append(f"Error packing table '{table}': {str(e)}")
                    all_good = False
            
            info_filename = f"pack_info_{datetime.now().strftime('%H%M%S')}.json"
            info_path = archive_dir / info_filename
            
            packed_tables = [r for r in results if isinstance(r, dict) and r.get('status') == 'ok']
            
            pack_info = {
                'time': datetime.now().isoformat(),
                'packed': len(packed_tables),
                'total': len(valid_tables),
                'results': results
            }
            
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(pack_info, f, ensure_ascii=False, indent=2, default=str)
            
            if all_good:
                return True, {
                    'msg': f"Pack complete",
                    'folder': str(archive_dir),
                    'packed': len(packed_tables),
                    'total': len(valid_tables),
                    'details': results
                }
            else:
                if packed_tables:
                    return True, {
                        'msg': f"Partially packed: {len(packed_tables)} of {len(valid_tables)}",
                        'folder': str(archive_dir),
                        'packed': len(packed_tables),
                        'total': len(valid_tables),
                        'details': results
                    }
                else:
                    return False, "Failed to pack any tables"
                
        except Exception as e:
            return False, f"Pack exception: {str(e)}"
    
    def pack_all_tables(self):
        tables = self.get_all_tables()
        return self.pack_tables(tables)
    
    def list_backups(self):
        backup_files = []
        for backup_dir in self.folders['backups'].iterdir():
            if backup_dir.is_dir():
                for file in backup_dir.glob("*.backup"):
                    backup_files.append({
                        'path': str(file),
                        'name': file.name,
                        'folder': backup_dir.name,
                        'size': file.stat().st_size,
                        'modified': datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                    })
        return sorted(backup_files, key=lambda x: x['folder'], reverse=True)
    
    def list_exports(self):
        export_files = []
        for export_dir in self.folders['exports'].iterdir():
            if export_dir.is_dir():
                for file in export_dir.glob("*"):
                    if file.is_file():
                        export_files.append({
                            'path': str(file),
                            'name': file.name,
                            'folder': export_dir.name,
                            'size': file.stat().st_size,
                            'modified': datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                        })
        return sorted(export_files, key=lambda x: x['folder'], reverse=True)
    
    def list_archives(self):
        archive_files = []
        for archive_dir in self.folders['archives'].iterdir():
            if archive_dir.is_dir():
                for file in archive_dir.glob("*"):
                    if file.is_file():
                        archive_files.append({
                            'path': str(file),
                            'name': file.name,
                            'folder': archive_dir.name,
                            'size': file.stat().st_size,
                            'modified': datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                        })
        return sorted(archive_files, key=lambda x: x['folder'], reverse=True)

db = DBManager()