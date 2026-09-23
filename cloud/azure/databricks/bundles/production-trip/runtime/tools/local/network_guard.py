"""로컬 Python 서버의 외부 TCP 연결과 DNS 조회 차단."""
import ipaddress
import socket


def install():
    def check(host):
        host=str(host)
        if host in ('localhost',socket.gethostname()):return
        try:allowed=ipaddress.ip_address(host).is_loopback
        except ValueError:allowed=False
        if not allowed:raise RuntimeError('로컬 모드 외부 연결 차단: '+host)
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    original_resolve=socket.getaddrinfo
    def connect(sock,address):
        if isinstance(address,tuple):check(address[0])
        return original_connect(sock,address)
    def connect_ex(sock,address):
        if isinstance(address,tuple):check(address[0])
        return original_connect_ex(sock,address)
    def resolve(host,*args,**kwargs):
        if host is not None:check(host)
        return original_resolve(host,*args,**kwargs)
    socket.socket.connect=connect
    socket.socket.connect_ex=connect_ex
    socket.getaddrinfo=resolve
