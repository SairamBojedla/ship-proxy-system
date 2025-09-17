#!/usr/bin/env python3


import socket
import threading
import struct
import queue
import logging
import argparse
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse
import ssl
import io


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RequestItem:
    
    def __init__(self, handler, method, url, headers, body):
        self.handler = handler
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body
        self.response_event = threading.Event()
        self.response = None
        self.error = None

class ShipProxy:
    def __init__(self, offshore_host='localhost', offshore_port=9999):
        self.offshore_host = offshore_host
        self.offshore_port = offshore_port
        self.request_queue = queue.Queue()
        self.tcp_sock = None
        self.connected = False
        self.running = False
        self.processor_thread = None

    def start(self):
        
        self.running = True

       
        if not self.connect_to_offshore():
            logger.error("Failed to connect to offshore proxy")
            return False

       
        self.processor_thread = threading.Thread(target=self.process_requests, daemon=True)
        self.processor_thread.start()

        logger.info("Ship proxy started successfully")
        return True

    def connect_to_offshore(self):
        
        try:
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((self.offshore_host, self.offshore_port))
            self.connected = True
            logger.info(f"Connected to offshore proxy at {self.offshore_host}:{self.offshore_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to offshore proxy: {e}")
            return False

    def process_requests(self):
        
        logger.info("Request processor started")

        while self.running:
            try:
                
                request_item = self.request_queue.get(timeout=1)

                if not self.connected:
                    request_item.error = "No connection to offshore proxy"
                    request_item.response_event.set()
                    continue

               
                request_str = self.build_request_string(request_item)

                
                try:
                    self.send_message(0, request_str.encode('utf-8'))

                    
                    response = self.read_response()
                    request_item.response = response

                except Exception as e:
                    logger.error(f"Error communicating with offshore proxy: {e}")
                    request_item.error = str(e)

                
                request_item.response_event.set()

                
                self.request_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in request processor: {e}")

    def build_request_string(self, request_item):
        
        request_str = f"{request_item.method} {request_item.url} HTTP/1.1\r\n"

        for header, value in request_item.headers.items():
            request_str += f"{header}: {value}\r\n"

        request_str += "\r\n"

        if request_item.body:
            request_str += request_item.body

        return request_str

    def send_message(self, msg_type, payload):
        
        length = len(payload)
        header = struct.pack('>I', length) + bytes([msg_type])
        self.tcp_sock.sendall(header + payload)

    def read_response(self):
        
        header = self._recv_all(5)
        if not header:
            raise Exception("Failed to read response header")

        length = struct.unpack('>I', header[:4])[0]
        msg_type = header[4]

        if msg_type != 1:
            raise Exception(f"Unexpected message type: {msg_type}")

        
        response_data = self._recv_all(length)
        if not response_data:
            raise Exception("Failed to read response data")

        return response_data

    def _recv_all(self, length):
        
        data = b''
        while len(data) < length:
            chunk = self.tcp_sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def queue_request(self, handler, method, url, headers, body):
        
        request_item = RequestItem(handler, method, url, headers, body)
        self.request_queue.put(request_item)
        return request_item

    def stop(self):
        
        self.running = False
        if self.tcp_sock:
            self.tcp_sock.close()
        logger.info("Ship proxy stopped")

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    

    def __init__(self, *args, ship_proxy=None, **kwargs):
        self.ship_proxy = ship_proxy
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def do_PUT(self):
        self.handle_request('PUT')

    def do_DELETE(self):
        self.handle_request('DELETE')

    def do_HEAD(self):
        self.handle_request('HEAD')

    def do_OPTIONS(self):
        self.handle_request('OPTIONS')

    def do_CONNECT(self):
        self.handle_request('CONNECT')

    def handle_request(self, method):
        
        try:
           
            url = self.path
            headers = dict(self.headers)

            
            body = ""
            if 'Content-Length' in headers:
                content_length = int(headers['Content-Length'])
                body = self.rfile.read(content_length).decode('utf-8')

            logger.info(f"Handling {method} request to {url}")

            
            request_item = self.ship_proxy.queue_request(self, method, url, headers, body)

            
            request_item.response_event.wait(timeout=60)  

            if request_item.error:
                self.send_error(502, f"Proxy Error: {request_item.error}")
                return

            if not request_item.response:
                self.send_error(504, "Gateway Timeout")
                return

            
            self.wfile.write(request_item.response)

        except Exception as e:
            logger.error(f"Error handling request: {e}")
            try:
                self.send_error(500, f"Internal Server Error: {str(e)}")
            except:
                pass

    def log_message(self, format, *args):
        
        logger.info(f"HTTP: {format % args}")

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    
    daemon_threads = True

def create_handler_class(ship_proxy):
    
    class Handler(ProxyHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, ship_proxy=ship_proxy, **kwargs)
    return Handler

def main():
    parser = argparse.ArgumentParser(description='Ship Proxy Client')
    parser.add_argument('--offshore-host', default='localhost', help='Offshore proxy host')
    parser.add_argument('--offshore-port', type=int, default=9999, help='Offshore proxy port')
    parser.add_argument('--proxy-port', type=int, default=8080, help='Local proxy port')

    args = parser.parse_args()

    
    ship_proxy = ShipProxy(args.offshore_host, args.offshore_port)

    if not ship_proxy.start():
        logger.error("Failed to start ship proxy")
        return

    
    handler_class = create_handler_class(ship_proxy)
    httpd = ThreadingHTTPServer(('0.0.0.0', args.proxy_port), handler_class)

    logger.info(f"Ship proxy listening on port {args.proxy_port}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down ship proxy...")
        ship_proxy.stop()
        httpd.shutdown()

if __name__ == '__main__':
    main()
