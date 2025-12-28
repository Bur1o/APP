from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import os
import json
from datetime import datetime
import tempfile
from pathlib import Path

import database as db_module
db = db_module.db

app = FastAPI(title="DataBoard", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/check")
async def check():
    return {"status": "active", "time": datetime.now().isoformat()}

try:
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
except Exception as e:
    print(f"Directory creation: {e}")

try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    print(f"Static mount: {e}")

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        tables = db.get_all_tables() or []
        table_counts = {}
        total_rows = 0
        
        for table in tables:
            count = db.get_row_count(table)
            table_counts[table] = count
            total_rows += count
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "tables": tables,
            "table_counts": table_counts,
            "total_rows": total_rows
        })
    except Exception as e:
        print(f"Dashboard error: {e}")
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "tables": [],
            "table_counts": {},
            "total_rows": 0
        })

@app.get("/tables", response_class=HTMLResponse)
async def table_editor(request: Request, table: str = "", page: int = 1):
    try:
        tables = db.get_all_tables() or []
        columns = []
        data = []
        total = 0
        pages = 0
        per_page = 200
        
        if table and table in tables:
            columns = db.get_table_info(table) or []
            total = db.get_row_count(table)
            pages = max(1, (total + per_page - 1) // per_page)
            
            if page < 1:
                page = 1
            if page > pages:
                page = pages
                
            offset = (page - 1) * per_page
            data = db.get_table_rows(table, limit=per_page, offset=offset) or []
        
        # Получаем количество записей для всех таблиц
        table_counts = {}
        for t in tables:
            table_counts[t] = db.get_row_count(t)
        
        return templates.TemplateResponse("table_editor.html", {
            "request": request,
            "tables": tables,
            "current_table": table,
            "columns": columns,
            "data": data,
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "table_counts": table_counts
        })
    except Exception as e:
        print(f"Table editor error: {e}")
        return templates.TemplateResponse("table_editor.html", {
            "request": request,
            "tables": [],
            "current_table": table,
            "columns": [],
            "data": [],
            "page": 1,
            "per_page": 200,
            "total": 0,
            "pages": 0,
            "table_counts": {}
        })

@app.post("/api/add")
async def add_row(request: Request):
    try:
        body = await request.json()
        table = body.get('table')
        data = body.get('data', {})
        
        if not table:
            return {"ok": False, "error": "Table required"}
        
        # Преобразуем пустые строки в None для nullable полей
        columns_info = db.get_table_info(table) or []
        nullable_columns = [col['column_name'] for col in columns_info if col['is_nullable'] == 'YES']
        
        for key in list(data.keys()):
            if data[key] == '' and key in nullable_columns:
                data[key] = None
        
        result = db.add_row(table, data)
        if result is not None:
            return {"ok": True, "msg": f"Запись добавлена", "id": result}
        else:
            return {"ok": True, "msg": "Запись добавлена"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/modify")
async def modify_row(request: Request):
    try:
        body = await request.json()
        table = body.get('table')
        data = body.get('data', {})
        condition = body.get('condition')
        
        if not table:
            return {"ok": False, "error": "Table required"}
        
        if not condition or condition.strip() == "":
            return {"ok": False, "error": "Condition required"}
        
        # Преобразуем пустые строки в None для nullable полей
        columns_info = db.get_table_info(table) or []
        nullable_columns = [col['column_name'] for col in columns_info if col['is_nullable'] == 'YES']
        
        for key in list(data.keys()):
            if data[key] == '' and key in nullable_columns:
                data[key] = None
        
        # Удаляем поля с пустыми значениями (кроме nullable)
        clean_data = {}
        for key, value in data.items():
            if value is not None and (value != '' or key in nullable_columns):
                clean_data[key] = value
        
        if not clean_data:
            return {"ok": False, "error": "Нет данных для изменения"}
        
        result = db.modify_row(table, clean_data, condition)
        return result
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/remove")
async def remove_row(request: Request):
    try:
        body = await request.json()
        table = body.get('table')
        condition = body.get('condition')
        cascade = body.get('cascade', False)
        
        if not table:
            return {"ok": False, "error": "Table required"}
        
        if not condition or condition.strip() == "":
            return {"ok": False, "error": "Condition required"}
        
        if cascade:
            result = db.remove_row(table, condition, cascade=True)
            return result
        else:
            result = db.safe_remove(table, condition)
            return result
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/drop_table")
async def drop_table(request: Request):
    try:
        body = await request.json()
        table = body.get('table')
        
        if not table:
            return {"ok": False, "error": "Table required"}
        
        result = db.drop_table_completely(table)
        if result:
            return {"ok": True, "msg": f"Table '{table}' dropped"}
        else:
            return {"ok": False, "error": f"Failed to drop '{table}'"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/wipe_all")
async def wipe_all_tables():
    try:
        ok, msg = db.wipe_database()
        
        if ok:
            return {
                "ok": True,
                "msg": msg,
                "dropped": msg.split(':')[-1].strip() if ':' in msg else 'unknown'
            }
        else:
            return {"ok": False, "error": msg}
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/get_table/{table_name}/{format}")
async def get_table(table_name: str, format: str):
    try:
        if format == "xlsx":
            filepath, filename = db.save_table_to_xlsx(table_name)
            if filepath:
                return FileResponse(
                    filepath,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=filename
                )
            else:
                return {"ok": False, "error": filename}
        
        elif format == "json":
            filepath, filename = db.save_table_to_json(table_name)
            if filepath:
                return FileResponse(
                    filepath,
                    media_type="application/json",
                    filename=filename
                )
            else:
                return {"ok": False, "error": filename}
        
        else:
            return {"ok": False, "error": "Format not supported"}
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/sql", response_class=HTMLResponse)
async def sql_console(request: Request):
    try:
        tables = db.get_all_tables() or []
        return templates.TemplateResponse("sql_console.html", {
            "request": request,
            "tables": tables
        })
    except Exception as e:
        print(f"SQL console error: {e}")
        return templates.TemplateResponse("sql_console.html", {
            "request": request,
            "tables": []
        })

@app.post("/api/run_sql")
async def run_sql(
    sql: str = Form(...),
    params: str = Form("")
):
    try:
        params_dict = {}
        if params and params.strip():
            try:
                params_dict = json.loads(params)
            except json.JSONDecodeError as e:
                return {"ok": False, "error": f"JSON error: {str(e)}"}
        
        result = db.run_sql(sql, params_dict)
        
        return {
            "ok": True,
            "data": result,
            "count": len(result) if result else 0
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/save_sql")
async def save_sql_result(
    sql: str = Form(...),
    params: str = Form(""),
    format: str = Form("csv")
):
    try:
        params_dict = {}
        if params and params.strip():
            try:
                params_dict = json.loads(params)
            except json.JSONDecodeError as e:
                return {"ok": False, "error": f"JSON error: {str(e)}"}
        
        result = db.run_sql(sql, params_dict)
        
        if not result:
            return {"ok": False, "error": "No data to save"}
        
        if format == "csv":
            filepath, error = db.save_query_to_csv(result)
            
            if filepath:
                filename = f"sql_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                return FileResponse(
                    filepath,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=filename
                )
            else:
                return {"ok": False, "error": error or "Save error"}
        
        elif format == "json":
            json_data = json.dumps(result, ensure_ascii=False, indent=2, default=str)
            filename = f"sql_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            return JSONResponse({
                "ok": True,
                "filename": filename,
                "content": json_data,
                "format": "json"
            })
        
        else:
            return {"ok": False, "error": f"Unknown format: {format}"}
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/save_tables")
async def save_selected_tables(
    tables: List[str] = Form(...),
    format: str = Form("xlsx")
):
    try:
        if not tables:
            return {"ok": False, "error": "No tables selected"}
        
        if format == "xlsx":
            filepath, error = db.save_tables_to_xlsx(tables)
            if filepath:
                return FileResponse(
                    filepath,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=Path(filepath).name
                )
            else:
                return {"ok": False, "error": error}
        
        elif format == "json":
            filepath, error = db.save_tables_to_json(tables)
            if filepath:
                return FileResponse(
                    filepath,
                    media_type="application/json",
                    filename=Path(filepath).name
                )
            else:
                return {"ok": False, "error": error}
        
        else:
            return {"ok": False, "error": "Format not supported"}
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/save_all/{format}")
async def save_all(format: str):
    try:
        if format == "xlsx":
            filepath, error = db.save_all_to_xlsx()
            if filepath:
                return FileResponse(
                    filepath,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=Path(filepath).name
                )
            else:
                return {"ok": False, "error": error}
        
        elif format == "json":
            filepath, error = db.save_all_to_json()
            if filepath:
                return FileResponse(
                    filepath,
                    media_type="application/json",
                    filename=Path(filepath).name
                )
            else:
                return {"ok": False, "error": error}
        
        else:
            return {"ok": False, "error": "Format not supported"}
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request):
    try:
        tables = db.get_all_tables() or []
        return templates.TemplateResponse("tools.html", {
            "request": request,
            "tables": tables
        })
    except Exception as e:
        print(f"Tools page error: {e}")
        return templates.TemplateResponse("tools.html", {
            "request": request,
            "tables": []
        })

@app.post("/api/backup")
async def backup_db():
    try:
        ok, backup_file, error = db.create_database_backup()
        
        if ok:
            return {
                "ok": True,
                "msg": f"Backup created: {backup_file}",
                "file": backup_file
            }
        else:
            return {"ok": False, "error": error}
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/restore")
async def restore_db(file: UploadFile = File(...)):
    try:
        if not file.filename:
            return {"ok": False, "error": "No file selected"}
        
        if not file.filename.lower().endswith('.backup'):
            return {"ok": False, "error": "Only .backup files supported"}
        
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file.filename)
        
        with open(temp_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        ok, msg = db.restore_from_backup(temp_path)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        if ok:
            return {
                "ok": True,
                "msg": msg + " - refreshing page..."
            }
        else:
            return {
                "ok": False,
                "error": msg
            }
            
    except Exception as e:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        
        return {"ok": False, "error": str(e)}

@app.post("/api/pack")
async def pack_tables(
    tables: str = Form("[]"),
    pack_all: bool = Form(False)
):
    try:
        if pack_all:
            ok, result = db.pack_all_tables()
        else:
            try:
                tables_list = json.loads(tables)
                if not isinstance(tables_list, list):
                    tables_list = []
            except:
                tables_list = []
            
            if not tables_list:
                return {"ok": False, "error": "Select tables to pack"}
            
            ok, result = db.pack_tables(tables_list)
        
        if ok:
            return {
                "ok": True,
                "msg": result["msg"],
                "folder": result["folder"],
                "packed": result["packed"],
                "total": result.get("total", 0),
                "details": result.get("details", [])
            }
        else:
            return {"ok": False, "error": result}
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Pack error: {str(e)}\n{error_details}")
        return {"ok": False, "error": str(e)}

@app.get("/api/get_file/{folder}/{filename}")
async def get_file(folder: str, filename: str):
    filepath = Path(folder) / filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    ext = filepath.suffix.lower()
    if ext == '.backup':
        media_type = "application/octet-stream"
    elif ext == '.xlsx':
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == '.json':
        media_type = "application/json"
    elif ext == '.sql':
        media_type = "text/plain"
    elif ext == '.csv':
        media_type = "text/csv"
    else:
        media_type = "application/octet-stream"
    
    return FileResponse(
        str(filepath),
        media_type=media_type,
        filename=filename
    )

@app.get("/api/list_backups")
async def list_backup_files():
    try:
        files = db.list_backups()
        return {"ok": True, "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/list_exports")
async def list_export_files():
    try:
        files = db.list_exports()
        return {"ok": True, "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/list_archives")
async def list_archive_files():
    try:
        files = db.list_archives()
        return {"ok": True, "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    host = os.getenv('APP_HOST', '0.0.0.0')
    port = int(os.getenv('APP_PORT', 3000))
    
    print(f"Server: http://localhost:{port}")
    print(f"Server: http://127.0.0.1:{port}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True
    )