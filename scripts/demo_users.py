"""Print a team credential mapping for Render; passwords are entered invisibly."""
import getpass
import json
from werkzeug.security import generate_password_hash


def main():
    users = {}
    print('Enter one unique username per person. Blank username finishes.')
    while True:
        name = input('Username: ').strip()
        if not name:
            break
        password = getpass.getpass('Password (at least 16 characters): ')
        if len(password) < 16:
            print('Use at least 16 characters.')
            continue
        if getpass.getpass('Confirm password: ') != password:
            print('Passwords did not match.')
            continue
        users[name] = generate_password_hash(password, method='pbkdf2:sha256:600000')
    if users:
        print('Paste this value into the Render DEMO_USERS_JSON secret; do not commit it:')
        print(json.dumps(users))


if __name__ == '__main__':
    main()
