from flask import Flask, g

from database import get_db_connection


app = Flask(__name__)

@app.teardown_appcontext
def close_db_connection(exception=None):
    connection = g.pop("db_connection", None)

    if connection is not None:
        connection.close()
        print("Database connection closed.")

@app.get("/health")
def health():
    return {
        "status": "ok",
        "message": "Backend is running"
    }

def get_db():
    if "db_connection" not in g:
        g.db_connection = get_db_connection()

    return g.db_connection

@app.get("/db-check")
def db_check():
    connection = get_db()

    result = connection.execute("SELECT 1").fetchone()

    return {
        "status": "ok",
        "database": "connected",
        "test_value": result[0]
    }


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )