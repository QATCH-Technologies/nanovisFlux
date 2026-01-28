import socket
import json
import threading

''' 
Overview of Interaction Between Socket Servers and Clients:

nanovisQ_endpoint.py (Client)          flux_socket_host.py (Server)
     Port 31951                          Port 31951 (HTTP)
         |                                   |
         |-------- User types 'c' -------->|
         |                                   |
         |-- Connect to port 31952 -------->| Command Server
         |-- Send command as JSON -------->|
         |<-- Receive acknowledgement ------|
         |                                   |
         |-- Connect to port 31951 -------->| HTTP Server
         |-- Send/receive HTTP requests -->|
'''

# Global variable to store queued commands
queued_command = None


def command_server(host='localhost', port=31952):
    """Server that listens for commands from nanovisQ_server"""
    global queued_command

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(2)
    print(f"Command server listening on {host}:{port}")

    try:
        while True:
            try:
                client_socket, addr = server.accept()
                print(f"Command received from {addr}")

                # Receive command
                request = client_socket.recv(4096).decode()

                # Parse JSON command
                try:
                    queued_command = json.loads(request)
                    print(f"Queued command: {queued_command}")

                    # Send acknowledgement
                    response = json.dumps(
                        {"status": "received", "command_id": 1})
                    client_socket.send(response.encode())
                except json.JSONDecodeError:
                    print("Failed to parse command JSON")
                    client_socket.send(json.dumps(
                        {"status": "error"}).encode())
                finally:
                    client_socket.close()
            except Exception as e:
                print(f"Error handling command: {e}")
    except KeyboardInterrupt:
        print("\nShutting down command server")
    finally:
        server.close()


def send_http_post(host, port, path, data):
    """Send HTTP POST request via socket and parse response"""
    global queued_command

    while True:
        try:
            # Create socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))

            print("Connected to server...")

            # Check if there's a queued command to send
            cmd_received = False
            if queued_command:
                print(f"Processing queued command: {queued_command}")
                cmd_received = True
            # else:
            #     print("No queued command")

            if cmd_received:
                # Queued command received, handle it
                print(f"Command Details: {queued_command}")
                # TODO: Process the command as needed
                # For now, just acknowledge it
                queued_command = None  # Clear the queue
                sock.close()
                continue

            # No command queued, prepare HTTP POST request
            body = json.dumps(data)
            request = (
                f"POST {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
                f"{body}"
            )

            # Send request
            sock.sendall(request.encode())

            # Receive response
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk

            sock.close()

            # Parse response
            response_str = response.decode()
            headers, body = response_str.split("\r\n\r\n", 1)
            print("Response Headers:")
            print(headers)
            print("\nResponse Body:")
            print(body)

            # print("Press 'q' to exit or Enter to open another Socket...")
            # if input().lower() == 'q':
            #     break

        except Exception as e:
            print(f"Error: {e}")
            raise e


if __name__ == "__main__":
    # Start command server in background thread
    cmd_thread = threading.Thread(target=command_server, daemon=True)
    cmd_thread.start()

    # Start HTTP client
    send_http_post("localhost", 31951, "/api/endpoint", {"key": "value"})
