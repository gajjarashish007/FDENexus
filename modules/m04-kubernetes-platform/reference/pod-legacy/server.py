#!/usr/bin/env python3
import subprocess
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

class PodPortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open('pod-portal.html', 'r') as f:
                self.wfile.write(f.read().encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/cleanup':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            env = os.environ.copy()
            env['DRY_RUN'] = 'true' if data.get('dryRun') else 'false'
            
            try:
                result = subprocess.run(['bash', 'pods.sh'], 
                                     capture_output=True, text=True, env=env)
                output = result.stdout + result.stderr
                
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(output.encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8080), PodPortalHandler)
    print("Pod Portal running at http://localhost:8080")
    server.serve_forever()
