import socket

server = 'irc.chat.twitch.tv'
port = 6667
nickname = 'your_nickname'  # Replace with your Twitch nickname
token = 'your_token'        # Replace with your Twitch token
channel = '#your_channel'   # Replace with the Twitch channel you want to connect to
target_user = 'target_username'  # Replace with the username of the user whose messages you want to track

def connect_to_twitch():
    sock = socket.socket()
    sock.connect((server, port))
    sock.send(f"PASS {token}\n".encode('utf-8'))
    sock.send(f"NICK {nickname}\n".encode('utf-8'))
    sock.send(f"JOIN {channel}\n".encode('utf-8'))
    return sock

def receive_messages(sock):
    try:
        while True:
            resp = sock.recv(2048).decode('utf-8')
            if len(resp) > 0:
                if f':{target_user}!' in resp:
                    print(resp)
    except KeyboardInterrupt:
        sock.close()

sock = connect_to_twitch()
receive_messages(sock)