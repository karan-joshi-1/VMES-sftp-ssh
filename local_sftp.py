# local_sftp.py - A simple SFTP server using FastAPI and Paramiko

from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List
import uvicorn
import os
import json
import time
import paramiko
import stat
from pydantic import BaseModel
import shared_state

# Models
class Client(BaseModel):
    hostIp: str
    username: str
    password: str

class ArgListFiles(BaseModel):
    hostIp: str
    username: str
    location: str

class ArgGetFile(BaseModel):
    hostIp: str
    username: str
    remotePath: str

class ArgPath(BaseModel):
    hostIp: str
    username: str
    path: str

class ArgOpNp(BaseModel):
    hostIp: str
    username: str
    oldPath: str
    newPath: str

class RetCls:
    @classmethod
    def ret(cls, status=False, msg='', data={}):
        return {
            'status': status,
            'msg': msg,
            'data': data
        }

# SSH Client
class SSHBoxClient:
    def __init__(self, ip='', port=22, username='root', password=''):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        
        # Create transport with faster window size
        self.t = paramiko.Transport((self.ip, self.port))
        self.t.window_size = 3 * 1024 * 1024
        self.t.packetizer.REKEY_BYTES = pow(2, 40)
        self.t.packetizer.REKEY_PACKETS = pow(2, 40)
        
        self.t.connect(username=self.username, password=self.password)
        self.t.use_compression()
        self.sftp = paramiko.SFTPClient.from_transport(self.t)
        
        # Set up SSH client for command execution
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(self.ip, self.port, self.username, self.password)
    
    def get_all_files_in_remote_dir(self, remote_dir):
        all_files = []

        if remote_dir[-1] == '/':
            remote_dir = remote_dir[0:-1]

        if remote_dir == '':
            remote_dir = '/'

        files = self.sftp.listdir_attr(remote_dir)

        for x in files:
            if remote_dir == '/':
                remote_dir = ''

            filename = remote_dir + '/' + x.filename
            file_item = {}
            file_item['name'] = x.filename
            file_item['path'] = filename
            file_item['size'] = x.st_size
            file_item['mTime'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(x.st_mtime))

            if stat.S_ISDIR(x.st_mode):
                file_item['type'] = 'dir'
            else:
                file_item['type'] = 'file'
            all_files.append(file_item)
        return all_files
    
    def put(self, local_path='', remote_path=''):
        try:
            self.sftp.put(localpath=local_path, remotepath=remote_path)
            return True
        except Exception as e:
            print(f"Error uploading file: {str(e)}")
            return False
    
    def get_file(self, remote_path='', local_path=''):
        try:
            pos = remote_path.rfind('/')
            local_filename = remote_path[pos:]
            
            if local_path[-1] == '/':
                local_path = local_path[:-1]
                
            save_path = local_path + local_filename
            self.sftp.get(remote_path, save_path)
            return True
        except Exception as e:
            print(f"Error downloading file: {str(e)}")
            return False
    
    def rename(self, old_path, new_path):
        try:
            self.sftp.rename(old_path, new_path)
            return True
        except Exception as e:
            print(f"Error renaming: {str(e)}")
            return False
    
    def remove(self, file_path):
        if file_path == '/':
            print(f"Cannot delete root directory")
            return False
            
        # Safety check for system directories
        protected_dirs = ['/bin', '/boot', '/dev', '/etc',
                        '/lib', '/opt', '/proc',
                        '/root', '/sbin', '/tmp', '/usr',
                        '/var']
        
        for d in protected_dirs:
            if file_path == d or file_path.startswith(d + '/'):
                print(f"Cannot delete protected directory: {file_path}")
                return False
                
        try:
            print(f"Attempting to delete: {file_path}")
            stdin, stdout, stderr = self.ssh.exec_command(f'rm -rf "{file_path}"')
            # Wait for the command to complete
            exit_status = stdout.channel.recv_exit_status()
            error = stderr.read().decode().strip()
            
            if exit_status != 0 or error:
                print(f"Error from server: {error}, exit status: {exit_status}")
                return False
                
            # Verify the file was actually deleted
            try:
                # Try to stat the file - if this succeeds, it wasn't deleted
                _, _, stderr = self.ssh.exec_command(f'stat "{file_path}"')
                exit_status = stderr.channel.recv_exit_status()
                
                if exit_status == 0:  # File still exists
                    print(f"File still exists after deletion attempt")
                    return False
            except:
                pass
                
            return True
        except Exception as e:
            print(f"Error removing: {str(e)}")
            return False
    
    def mkdir(self, dir_path):
        try:
            self.sftp.mkdir(dir_path)
            return True
        except Exception as e:
            print(f"Error creating directory: {str(e)}")
            return False
    
    def get_history(self):
        try:
            rets = []
            _, stdout, _ = self.ssh.exec_command("cat ~/.bash_history")
            for item in stdout.readlines():
                if item[0] == '#':
                    continue
                rets.append(item.strip())
            return rets
        except Exception as e:
            print(f"Error getting history: {str(e)}")
            return []
    
    def get_df(self):
        try:
            rets = []
            _, stdout, _ = self.ssh.exec_command("df -lh")
            for item in stdout.readlines():
                rets.append(item.strip())
            return rets
        except Exception as e:
            print(f"Error getting disk usage: {str(e)}")
            return []
    
    def close(self):
        try:
            self.t.close()
            self.ssh.close()
        except:
            pass
    
    def open_shell(self, term="xterm", width=80, height=24):
        """
        Open an interactive shell channel with a PTY.
        """
        chan = self.t.open_session()
        chan.get_pty(term=term, width=width, height=height)
        chan.invoke_shell()
        return chan
    
# Initialize FastAPI app
app = FastAPI(title="Local SFTP")

# Configuration
config = {
    "origins": ["http://localhost:8000", "http://127.0.0.1:8000"],
    "tmp_path": "./dtmp/",
    "upload_tmp_path": "./utmp/",
    "share_path": "./share/",
    "port": 8000
}

# Client database to store connections
client_db = {}

# Ensure directories exist
for directory in [config["tmp_path"], config["upload_tmp_path"], config["share_path"]]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config["origins"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
@app.post("/login")
async def login(client: Client):
    try:
        pos = client.hostIp.find(':')
        if pos >= 0:
            ip = client.hostIp[:pos]
            port = int(client.hostIp[pos+1:])
        else:
            ip = client.hostIp
            port = 22
            
        ssh_client = SSHBoxClient(ip=ip, port=port, username=client.username, password=client.password)
        key = client.hostIp + client.username
        client_db[key] = ssh_client
        
        # Save to shared state
        shared_state.save_client(key, ip, port, client.username, client.password)
        
        data = {
            'key': key, 
            'hostIp': client.hostIp, 
            'username': client.username
        }
        return RetCls.ret(True, 'Login successful', data)
    except Exception as e:
        return RetCls.ret(False, str(e), {})

@app.post("/listFiles")
async def list_files(arg_list_files: ArgListFiles):
    try:
        key = arg_list_files.hostIp + arg_list_files.username
        if key not in client_db:
            return RetCls.ret(False, "Not logged in", {})
            
        ssh_client = client_db[key]
        all_files = ssh_client.get_all_files_in_remote_dir(arg_list_files.location)
        return RetCls.ret(True, '', all_files)
    except Exception as e:
        return RetCls.ret(False, str(e), [{}])

@app.post("/uploadfile")
async def upload_file(request: Request, file: UploadFile = File(...)):
    try:
        # Get upload parameters from headers
        upload_params = json.loads(request.headers.get('upload-params', '{}'))
        host_ip = upload_params.get('hostIp', '')
        username = upload_params.get('username', '')
        location = upload_params.get('location', '')
        
        if not all([host_ip, username, location]):
            return RetCls.ret(False, "Missing upload parameters", {})
        
        key = host_ip + username
        if key not in client_db:
            return RetCls.ret(False, "Not logged in", {})
        
        ssh_client = client_db[key]
        
        # Save uploaded file temporarily
        local_path = os.path.join(config["upload_tmp_path"], file.filename)
        with open(local_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        # Upload to remote server
        remote_path = location + '/' + file.filename
        success = ssh_client.put(local_path, remote_path)
        
        # Clean up temporary file
        os.remove(local_path)
        
        if success:
            return RetCls.ret(True, "File uploaded successfully", {"filename": file.filename})
        else:
            return RetCls.ret(False, "Failed to upload file", {})
    except Exception as e:
        return RetCls.ret(False, str(e), {})

@app.post("/getFile")
async def get_file(arg_get_file: ArgGetFile):
    try:
        key = arg_get_file.hostIp + arg_get_file.username
        if key not in client_db:
            return RetCls.ret(False, "Not logged in", {})
            
        ssh_client = client_db[key]
        pos = arg_get_file.remotePath.rfind('/')
        file_name = arg_get_file.remotePath[pos:]
        
        success = ssh_client.get_file(arg_get_file.remotePath, config["tmp_path"])
        if not success:
            return RetCls.ret(False, "Failed to download file", {})
        
        path = config["tmp_path"] + file_name
        path = path.replace('//', '/')
        
        return FileResponse(path)
    except Exception as e:
        return RetCls.ret(False, str(e), {})

@app.post("/mkdir")
async def mkdir(arg_mkdir: ArgPath):
    try:
        key = arg_mkdir.hostIp + arg_mkdir.username
        if key not in client_db:
            return RetCls.ret(False, "Not logged in", {})
            
        ssh_client = client_db[key]
        success = ssh_client.mkdir(arg_mkdir.path)
        
        if success:
            return RetCls.ret(True, "Directory created", {})
        else:
            return RetCls.ret(False, "Failed to create directory", {})
    except Exception as e:
        return RetCls.ret(False, str(e), {})

@app.post("/remove")
async def remove(arg_remove: ArgPath):
    try:
        key = arg_remove.hostIp + arg_remove.username
        if key not in client_db:
            return RetCls.ret(False, "Not logged in", {})
            
        ssh_client = client_db[key]
        success = ssh_client.remove(arg_remove.path)
        
        if success:
            return RetCls.ret(True, "File/directory removed", {})
        else:
            return RetCls.ret(False, "Failed to remove or path protected", {})
    except Exception as e:
        return RetCls.ret(False, str(e), {})

@app.post("/rename")
async def rename(arg_rename: ArgOpNp):
    try:
        key = arg_rename.hostIp + arg_rename.username
        if key not in client_db:
            return RetCls.ret(False, "Not logged in", {})
            
        ssh_client = client_db[key]
        success = ssh_client.rename(arg_rename.oldPath, arg_rename.newPath)
        
        if success:
            return RetCls.ret(True, "File/directory renamed", {})
        else:
            return RetCls.ret(False, "Failed to rename", {})
    except Exception as e:
        return RetCls.ret(False, str(e), {})

@app.post("/getHistory")
async def get_history(arg: ArgPath):
    try:
        key = arg.hostIp + arg.username
        if key not in client_db:
            return RetCls.ret(False, "Not logged in", {})
            
        ssh_client = client_db[key]
        history = ssh_client.get_history()
        return RetCls.ret(True, '', history)
    except Exception as e:
        return RetCls.ret(False, str(e), [])

@app.post("/getDf")
async def get_df(arg: ArgPath):
    try:
        key = arg.hostIp + arg.username
        if key not in client_db:
            return RetCls.ret(False, "Not logged in", {})
            
        ssh_client = client_db[key]
        df_info = ssh_client.get_df()
        return RetCls.ret(True, '', df_info)
    except Exception as e:
        return RetCls.ret(False, str(e), [])

@app.get("/")
async def main():
    return RedirectResponse("/static/index.html")

# Mount static files 
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/share", StaticFiles(directory="share"), name="share")

# Run the app
if __name__ == "__main__":
    print("Starting Local SFTP server...")
    print(f"Server running at http://localhost:{config['port']}")
    uvicorn.run(app, host="0.0.0.0", port=config["port"])