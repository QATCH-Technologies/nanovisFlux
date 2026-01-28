import socket
import json


def send_command(host='localhost', port=31952, command_json=None):
    """Client that sends commands to the flux_app_client command server"""
    if command_json is None:
        command_json = {"command": "do_something",
                        "parameters": {"param1": 42, "param2": "value"}}

    try:
        # Connect to command server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        print(f"Connected to command server on {host}:{port}")

        # Send command as JSON
        command_str = json.dumps(command_json)
        sock.sendall(command_str.encode())
        print(f"Command sent: {command_json}")

        # Receive acknowledgement
        ack = sock.recv(4096).decode()
        print(f"Acknowledgement: {ack}")

        sock.close()
    except Exception as e:
        print(f"Error sending command: {e}")


def handle_client(client_socket):
    request = client_socket.recv(4096).decode()

    # Parse HTTP request body
    body_start = request.find('\r\n\r\n')
    if body_start != -1:
        body = request[body_start + 4:]
        try:
            json_data = json.loads(body)
        except json.JSONDecodeError:
            json_data = {}
    else:
        json_data = {}

    # Create response
    response_data = {
        "received": json_data,
        "result": "SUCCESS"
    }

    response_body = json.dumps(response_data)
    response = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(response_body)}\r\n"
        "\r\n"
        + response_body
    )

    client_socket.send(response.encode())
    client_socket.close()


def start_server(host='localhost', port=31951):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(2)
    print(f"Server listening on {host}:{port}")
    print("Press Ctrl-C to stop the server")

    try:
        while True:
            print("\nPress 'c' to queue a command for the client")
            print("or Enter to wait for client query...")
            user_input = input().strip().lower()

            if user_input == 'c':
                # Get command from user or use default
                command_json = {
                    "command": "do_something",
                    "parameters": {"param1": 42, "param2": "value"}
                }
                print(f"Queueing command: {command_json}")

                # Send command to client via command socket
                send_command(command_json=command_json)

            print(f"Waiting for a connection...")
            client_socket, addr = server.accept()
            print(f"Connection from {addr}")
            handle_client(client_socket)
    except KeyboardInterrupt:
        print("\nShutting down server")
    finally:
        server.close()


if __name__ == "__main__":
    start_server()
