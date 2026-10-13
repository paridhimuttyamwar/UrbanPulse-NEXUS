import mysql.connector

candidates = ['', 'root', 'root123', 'admin', 'password', '1234', '123456', '12345678', 'mysql', 'Dell@123', 'root@123']
found = None

for pw in candidates:
    try:
        conn = mysql.connector.connect(
            host='localhost',
            port=3306,
            user='root',
            password=pw,
            connection_timeout=3
        )
        if conn.is_connected():
            found = pw
            print(f"CONNECTED_SUCCESS: password='{pw}'")
            conn.close()
            break
    except Exception as e:
        # print error for first one to see error type
        if pw == '':
            print(f"Attempt failed: {e}")

if not found:
    print("NO_PASSWORD_MATCHED")
