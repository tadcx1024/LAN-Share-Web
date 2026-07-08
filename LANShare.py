import html
import http.server
import mimetypes
import os
import posixpath
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
import base64
import socketserver
import socket
import argparse




NEED_AUTH=False
USERNAME = '666'
PASSWORD = '666'
AUTH_KEY = base64.b64encode('{}:{}'.format(USERNAME, PASSWORD).encode()).decode()

port = 80


class SimpleHTTPRequestHandler(socketserver.ThreadingMixIn,http.server.BaseHTTPRequestHandler):
    daemon_threads = True

    #身份验证
    def do_AUTHHEAD(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="FileServer"')
        self.send_header("Content-type", "text/html")
        self.end_headers()

    #根据是否需要身份验证返回内容
    def do_GET(self):
        #不需要身份验证
        if not NEED_AUTH:
            self.do_GET_file()
        #需要身份验证
        else:
            """ Present frontpage with user authentication. """
            # print("收到",self.headers.get("Authorization"))
            # 未认证
            if self.headers.get("Authorization") == None:
                self.do_AUTHHEAD()
                self.wfile.write(b"no auth header received")
            # 通过认证
            elif self.headers.get("Authorization") == "Basic " + AUTH_KEY:  # Digest/Basic
                self.do_GET_file()
            else:
                self.do_AUTHHEAD()
                self.wfile.write(self.headers.get("Authorization").encode())
                self.wfile.write(b"not authenticated")

    #通过认证后返回内容
    def do_GET_file(self):
       # print(self.send_header('Content-Type', 'text/html; charset=utf-8'))
        f = self.send_head()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    #发送网页内容
    def send_head(self):
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.send_header('Content-Type', 'text/html; charset=utf-8')  # utf8编码指定
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)

        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            f = open(path, 'rb')
        except IOError:
            self.send_error(404, "File not found")
            return None
        self.send_response(200)

        self.send_header('Content-Type', 'text/html; charset=utf-8') #utf8编码指定
        fs = os.fstat(f.fileno())
        self.send_header("Content-Length", str(fs[6]))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return f

    #文件路径处理
    def translate_path(self, path):
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        path = posixpath.normpath(urllib.parse.unquote(path))
        words = path.split('/')
        words = [_f for _f in words if _f]
        path = os.getcwd()
        for word in words:
            drive, word = os.path.splitdrive(word)
            head, word = os.path.split(word)
            if word in (os.curdir, os.pardir): continue
            path = os.path.join(path, word)
        return path

    #列出文件夹文件
    def list_directory(self, path):
        try:
            list = os.listdir(path)
        except os.error:
            self.send_error(404, "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        f = BytesIO()
        displaypath =os.getcwd()+(html.escape(urllib.parse.unquote(self.path)))
        #displaypath = html.escape(urllib.parse.unquote(self.path))
        f.write(b'<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
        f.write(("<html>\n<title>Directory listing for %s</title>\n" % displaypath).encode())
        f.write(("<body bgcolor='E0E0E0'>\n<h2>Directory listing for %s</h2>\n" % displaypath).encode()) #颜色白灰E0E0E0
        f.write(b"<hr>\n")
        f.write(b"<form ENCTYPE=\"multipart/form-data\" method=\"post\">")
        f.write(b"<input name=\"file\" type=\"file\" multiple/>") #多文件的话末尾加上multiple
        f.write(b"<input type=\"submit\" value=\"upload\"/></form>\n")
        f.write(b"<hr>\n<ul>\n")
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                #文件夹处理
                displayname = name + "/"
                linkname = name + "/"
                f.write(('<li><a href="%s" >%s</a>\n' % (linkname, html.escape(displayname))).encode())  # 添加download，通过三个%s传参
            elif os.path.islink(fullname):
                #链接处理
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
                f.write(('<li><a href="%s" >%s</a>\n' % (linkname, html.escape(displayname))).encode()) #添加download，通过三个%s传参
            else:
                #普通文件下载
                #f.write(('<li><a href="%s" download="%s" >%s</a>\n' % (urllib.parse.quote(linkname),linkname, html.escape(displayname))).encode())  #文件名经过urllib.parse.quote编码,下载会乱码,去除
                f.write(('<li><a href="%s" download="%s" >%s</a>\n' % (linkname,linkname, html.escape(displayname))).encode())  # 添加download，通过三个%s传参。

        f.write(b"</ul>\n<hr>\n</body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        #self.send_header("Content-type", "text/html")
        self.send_header('Content-Type', 'text/html; charset=utf-8') #utf8编码指定
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return f

    # 上传文件
    def do_POST(self):
        r, info = self.deal_post_data()
        print((r, info, "by: ", self.client_address))
        f = BytesIO()
        f.write(b'<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
        f.write(b"<html>\n<title>Upload Result Page</title>\n")
        f.write(b"<body>\n<h2>Upload Result Page</h2>\n")
        f.write(b"<hr>\n")
        if r:
            f.write(b"<strong> <font size='5'> Success </font> </strong>")
        else:
            f.write(b"<strong>Failed:</strong>")
        f.write(info.encode())
        f.write(("<br><a href=\"%s\">back</a>" % self.headers['referer']).encode())
        f.write(b"</body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')  # utf8编码指定
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    # 处理HTTP请求，写入文件载荷
    def deal_post_data(self):
        content_type = self.headers['content-type']
        if not content_type:
            return (False, "Content-Type header doesn't contain boundary")
        boundary = content_type.split("=")[1].encode()

        remainbytes = int(self.headers['content-length'])

        # 第一行boundary
        line = self.rfile.readline()
        remainbytes -= len(line)
        if not boundary in line:
            return (False, "Content NOT begin with boundary")

        fntext=""
        while True:
            #第二行文件名
            line = self.rfile.readline()
            remainbytes -= len(line)
            fn = re.findall(r'Content-Disposition.*name="file"; filename="(.*)"', line.decode())
            if not fn:
                return (False, "Can't find out file name...")
            path = self.translate_path(self.path)
            fn = os.path.join(path, fn[0])
            fntext=fntext+fn+ "<br>" #返回信息拼接

            line = self.rfile.readline() #行3
            remainbytes -= len(line)

            line = self.rfile.readline() #行4
            remainbytes -= len(line)

            try:
                out = open(fn, 'wb')
            except IOError:
                return (False, "Can't create file to write, do you have permission to write?")

            #文件载荷
            preline = self.rfile.readline()
            remainbytes -= len(preline)
            #print("PRELINE" , preline,"boundary",boundary)
            #preline前一行 line最新行，用于判断边界
            while remainbytes>0:
                line = self.rfile.readline()
                remainbytes -= len(line)
                #print(remainbytes)
                if boundary in line: #最新一行遇到边界 写入上一行
                    preline = preline[0:-1]
                    if preline.endswith(b'\r'):
                        preline = preline[0:-1]
                    out.write(preline)
                    out.close()
                    #print("DONE")
                    break
                else:
                    #print("CONTEXT", preline)
                    out.write(preline)
                    preline = line

            #出循环页面结果返回

            if remainbytes == 0:
                return (True, "<br><br>File: <br> %s upload success!<br>" % fntext)
            elif remainbytes < 0:
                return (False, "Unexpect Ends of data.")

    #文件复制
    def copyfile(self, source, outputfile):
        shutil.copyfileobj(source, outputfile)




#IP展示
def get_ip():
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return local_ip

if __name__ == '__main__':
    ip=get_ip()

    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', '-b', default=ip, metavar='ADDRESS',
                        help='Specify alternate bind address '
                             '[default: all interfaces]')
    parser.add_argument('--port', '-p', default=port, type=int,
                        help='Specify alternate port [default: 80]')
    args = parser.parse_args()

    http.server.test(HandlerClass=SimpleHTTPRequestHandler, port=args.port, bind=args.bind)






