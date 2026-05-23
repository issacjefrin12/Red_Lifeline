import os
from urllib.parse import urlparse, unquote


def _first_env(*names, default=None):
    for name in names:
        value = os.getenv(name)
        if value is not None and value != "":
            return value
    return default


def _parse_mysql_url(url):
    if not url:
        return {}

    parsed = urlparse(url)
    if parsed.scheme not in ("mysql", "mysql+mysqlconnector"):
        return {}

    return {
        "host": parsed.hostname,
        "port": parsed.port,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "database": parsed.path.lstrip("/") if parsed.path else None,
    }


def _is_cloud_runtime():
    return any(
        os.getenv(name)
        for name in ("RENDER", "RENDER_EXTERNAL_HOSTNAME", "RAILWAY_PROJECT_ID")
    )


def get_db_config():
    """Return MySQL connection settings from common env var names."""
    # Prefer explicit DB_URL, then Railway public URL, then other URL-style vars.
    mysql_url = _first_env("DB_URL", "MYSQL_PUBLIC_URL", "MYSQL_URL", "DATABASE_URL")
    parsed_url = _parse_mysql_url(mysql_url)

    # Prefer explicit DB_* vars. If absent, use parsed URL values before MYSQL*.
    host = _first_env("DB_HOST", "BBMS_DB_HOST", default=parsed_url.get("host"))
    if host is None:
        host = _first_env("MYSQLHOST", default="localhost")

    user = _first_env("DB_USER", "BBMS_DB_USER", default=parsed_url.get("user"))
    if user is None:
        user = _first_env("MYSQLUSER", default="root")

    password = _first_env("DB_PASSWORD", "BBMS_DB_PASSWORD", default=parsed_url.get("password"))
    if password is None:
        password = _first_env("MYSQLPASSWORD", default="jefrin")

    database = _first_env("DB_NAME", "BBMS_DB_NAME", default=parsed_url.get("database"))
    if database is None:
        database = _first_env("MYSQLDATABASE", "MYSQL_DATABASE", default="blood_bank_db")

    parsed_port = parsed_url.get("port")
    port = int(
        _first_env(
            "DB_PORT",
            "BBMS_DB_PORT",
            default=str(parsed_port) if parsed_port else None,
        )
        or _first_env("MYSQLPORT", default="3306")
    )

    if _is_cloud_runtime() and host in ("localhost", "127.0.0.1"):
        raise RuntimeError(
            "Database host resolved to localhost in cloud runtime. "
            "Set DB_HOST/DB_PORT (or MYSQLHOST/MYSQLPORT) to your remote MySQL."
        )

    return {
        "host": host,
        "user": user,
        "password": password,
        "database": database,
        "port": port,
        "connection_timeout": int(_first_env("DB_CONNECT_TIMEOUT", "BBMS_DB_CONNECT_TIMEOUT", default="10")),
    }
