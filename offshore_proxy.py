#!/usr/bin/env python3
"""
Offshore Proxy Server
Receives requests from ship proxy over a single TCP connection and forwards them to destination servers.
"""

import socket
import threading
import struct
import json
import logging
import argparse
from urllib.parse import urlparse
import ssl
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OffshoreProxy:
    def __init__(self, host='0.0.0.0', port=9999):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False

    def start(self):
        """Start the offshore proxy server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            self.running = True

            logger.info(f"Offshore proxy listening on {self.host}:{self.port}")

            while self.running:
                try:
                    conn, addr = self.socket.accept()
                    logger.info(f"Connection established with ship proxy: {addr}")
                    self.handle_ship_connection(conn)
                except socket.error as e:
                    if self.running:
                        logger.error(f"Socket error: {e}")

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
        finally:
            self.cleanup()

    def handle_ship_connection(self, conn):
        """Handle persistent connection from ship proxy"""
        try:
            while self.running:
                # Read message header (4 bytes length + 1 byte type)
                header = self._recv_all(conn, 5)
                if not header:
                    break

                length = struct.unpack('>I', header[:4])[0]
                msg_type = header[4]

                if msg_type != 0:  # Expect request type
                    logger.warning(f"Unexpected message type: {msg_type}")
                    continue

                # Read request data
                request_data = self._recv_all(conn, length)
                if not request_data:
                    break

                # Process the request
                response = self.process_request(request_data)

                # Send response back
                self.send_message(conn, 1, response)

        except Exception as e:
            logger.error(f"Error handling ship connection: {e}")
        finally:
            conn.close()
            logger.info("Ship connection closed")

    def process_request(self, request_data):
        """Process HTTP request and return response"""
        try:
            request_str = request_data.decode('utf-8')
            lines = request_str.split('\r\n')
            request_line = lines[0]

            method, url, version = request_line.split(' ', 2)

            if method == 'CONNECT':
                # Handle HTTPS CONNECT request
                return self.handle_connect_request(url)
            else:
                # Handle regular HTTP request
                return self.handle_http_request(request_str, url)

        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return self.create_error_response(500, "Internal Server Error")

    def handle_http_request(self, request_str, url):
        """Handle regular HTTP requests"""
        try:
            parsed_url = urlparse(url)
            host = parsed_url.hostname
            port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)

            if not host:
                # Extract host from headers if not in URL
                lines = request_str.split('\r\n')
                for line in lines[1:]:
                    if line.lower().startswith('host:'):
                        host = line.split(':', 1)[1].strip()
                        break

            if not host:
                return self.create_error_response(400, "Bad Request - No host specified")

            # Create connection to target server
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.settimeout(30)
            target_sock.connect((host, port))

            # Send request to target server
            target_sock.sendall(request_str.encode('utf-8'))

            # Read response from target server
            response = b''
            target_sock.settimeout(5)
            while True:
                try:
                    chunk = target_sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                except socket.timeout:
                    break

            target_sock.close()
            return response

        except Exception as e:
            logger.error(f"Error handling HTTP request: {e}")
            return self.create_error_response(502, "Bad Gateway")

    def handle_connect_request(self, target):
        """Handle HTTPS CONNECT requests"""
        try:
            # For CONNECT method, just return connection established
            # In a real implementation, this would set up tunneling
            response = "HTTP/1.1 200 Connection Established\r\n\r\n"
            return response.encode('utf-8')
        except Exception as e:
            logger.error(f"Error handling CONNECT request: {e}")
            return self.create_error_response(502, "Bad Gateway")

    def create_error_response(self, status_code, status_text):
        """Create HTTP error response"""
        response = f"""HTTP/1.1 {status_code} {status_text}\r
Content-Type: text/html\r
Content-Length: 54\r
\r
<html><body><h1>{status_code} {status_text}</h1></body></html>"""
        return response.encode('utf-8')

    def send_message(self, sock, msg_type, payload):
        """Send message with protocol framing"""
        length = len(payload)
        header = struct.pack('>I', length) + bytes([msg_type])
        sock.sendall(header + payload)

    def _recv_all(self, sock, length):
        """Receive exactly length bytes"""
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def stop(self):
        """Stop the proxy server"""
        self.running = False
        if self.socket:
            self.socket.close()

    def cleanup(self):
        """Clean up resources"""
        if self.socket:
            self.socket.close()
            logger.info("Offshore proxy stopped")

def main():
    parser = argparse.ArgumentParser(description='Offshore Proxy Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=9999, help='Port to bind to')

    args = parser.parse_args()

    proxy = OffshoreProxy(args.host, args.port)

    try:
        proxy.start()
    except KeyboardInterrupt:
        logger.info("Shutting down offshore proxy...")
        proxy.stop()

if __name__ == '__main__':
    main()
