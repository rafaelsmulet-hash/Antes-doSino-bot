"""Cria a primeira conta admin (ou promove/reseta a senha de uma já existente).

Uso:
    python seed_admin.py <usuario> <senha> [nome de exibição]
"""
import sys

from db import get_conn, init_db, now_str
from werkzeug.security import generate_password_hash


def main():
    if len(sys.argv) < 3:
        print("Uso: python seed_admin.py <usuario> <senha> [nome de exibição]")
        sys.exit(1)

    username = sys.argv[1].strip()
    password = sys.argv[2]
    display_name = sys.argv[3].strip() if len(sys.argv) > 3 else username

    init_db()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        password_hash = generate_password_hash(password)
        if existing:
            conn.execute(
                "UPDATE users SET password_hash = ?, display_name = ?, is_admin = 1 WHERE id = ?",
                (password_hash, display_name, existing["id"]),
            )
            print(f"Usuário '{username}' já existia — senha redefinida e promovido a admin.")
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, display_name, is_admin, created_at) VALUES (?, ?, ?, 1, ?)",
                (username, password_hash, display_name, now_str()),
            )
            print(f"Admin '{username}' criado com sucesso.")


if __name__ == "__main__":
    main()
