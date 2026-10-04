from getpass import getpass

import core


def main():
    username = input("Username: ").strip()
    full_name = input("Full name: ").strip()
    if not username or not full_name:
        print("Username and full name are both required.")
        return
    pw = getpass("Password (min 8 characters): ")
    if len(pw) < 8:
        print("Password too short - use at least 8 characters.")
        return
    if pw != getpass("Repeat password: "):
        print("Passwords did not match.")
        return
    core.run("INSERT INTO staff_accounts (username, password_hash, full_name) VALUES (%s,%s,%s) "
             "ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash), full_name=VALUES(full_name), "
             "failed_attempts=0, locked_until=NULL, active=1",
             (username, core.hash_password(pw), full_name), write=True)
    print(f"Account '{username}' saved.")


if __name__ == "__main__":
    main()
    