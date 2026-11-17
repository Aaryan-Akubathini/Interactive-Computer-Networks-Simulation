"""Create the MySQL database (if missing) and all tables.   Usage: python init_db.py"""
from sqlalchemy import create_engine, text

import database
import models  # noqa: F401  (registers the tables)


def main():
    admin = create_engine(database.db_url(with_database=False), connect_args={"connect_timeout": 5})
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{database.DB_NAME}` "
                          "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        conn.commit()
    database.Base.metadata.create_all(database.engine)
    print(f"Database '{database.DB_NAME}' is ready (tables: topologies, simulation_runs).")


if __name__ == "__main__":
    main()
