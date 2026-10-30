import os
import pymysql
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()


def get_connection():
    try:
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "campuspro"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False
        )
    except Exception:
        return None


def init_db():
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    db_name = os.getenv("DB_NAME", "campuspro")

    if not db_name.replace("_", "").isalnum():
        raise ValueError("Invalid database name in DB_NAME.")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(190) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role ENUM('student', 'faculty', 'admin')
                        NOT NULL DEFAULT 'student',
                    department VARCHAR(100)
                        NOT NULL DEFAULT 'CSE',
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB
            """)

            cur.execute("SHOW COLUMNS FROM users")
            user_columns = {row["Field"] for row in cur.fetchall()}

            if "department" not in user_columns:
                cur.execute("""
                    ALTER TABLE users
                    ADD COLUMN department VARCHAR(100)
                    NOT NULL DEFAULT 'CSE'
                """)

            if "is_active" not in user_columns:
                cur.execute("""
                    ALTER TABLE users
                    ADD COLUMN is_active TINYINT(1)
                    NOT NULL DEFAULT 1
                """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    abstract TEXT NOT NULL,
                    tech_stack VARCHAR(255) DEFAULT '',
                    owner_id INT NOT NULL,
                    project_link VARCHAR(2048) DEFAULT NULL,
                    image_paths LONGTEXT DEFAULT NULL,
                    status ENUM(
                        'Submitted',
                        'Under Review',
                        'Approved',
                        'Needs Changes'
                    ) NOT NULL DEFAULT 'Submitted',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_projects_owner
                        FOREIGN KEY (owner_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB
            """)

            cur.execute("SHOW COLUMNS FROM projects")
            project_columns = {row["Field"] for row in cur.fetchall()}

            if "tech_stack" not in project_columns:
                cur.execute("""
                    ALTER TABLE projects
                    ADD COLUMN tech_stack VARCHAR(255) DEFAULT ''
                """)

            if "project_link" not in project_columns:
                cur.execute("""
                    ALTER TABLE projects
                    ADD COLUMN project_link VARCHAR(2048) DEFAULT NULL
                """)

            if "image_paths" not in project_columns:
                cur.execute("""
                    ALTER TABLE projects
                    ADD COLUMN image_paths LONGTEXT DEFAULT NULL
                """)

            if "status" not in project_columns:
                cur.execute("""
                    ALTER TABLE projects
                    ADD COLUMN status ENUM(
                        'Submitted',
                        'Under Review',
                        'Approved',
                        'Needs Changes'
                    ) NOT NULL DEFAULT 'Submitted'
                """)

            if "owner_id" not in project_columns:
                if "student_id" in project_columns:
                    cur.execute("""
                        ALTER TABLE projects
                        ADD COLUMN owner_id INT NULL
                    """)
                    cur.execute("""
                        UPDATE projects
                        SET owner_id = student_id
                        WHERE owner_id IS NULL
                    """)
                    cur.execute("""
                        ALTER TABLE projects
                        MODIFY owner_id INT NOT NULL
                    """)
                    cur.execute("""
                        ALTER TABLE projects
                        ADD INDEX idx_projects_owner_id (owner_id)
                    """)
                    cur.execute("""
                        ALTER TABLE projects
                        ADD CONSTRAINT fk_projects_owner_migrated
                        FOREIGN KEY (owner_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                    """)

            admin_email = os.getenv("ADMIN_EMAIL", "admin@campuspro.local").strip().lower()
            admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")

            cur.execute("SELECT id FROM users WHERE email = %s", (admin_email,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO users
                        (name, email, password_hash, role, department, is_active)
                    VALUES (%s, %s, %s, 'admin', %s, 1)
                """, (
                    "CampusPro Admin",
                    admin_email,
                    generate_password_hash(admin_password),
                    "Administration"
                ))

        print("CampusPro database initialized successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
