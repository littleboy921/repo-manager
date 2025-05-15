import re
from typing import Tuple
# 定义函数：验证address及port是否合法，返回是否合法及错误信息
def is_valid_address_port(address:str='8.8.8.8',port:str='8888')->Tuple[bool,str]:
    # 验证ip地址或域名是否合法
    # 如果只包含数字和.,则按照ip地址规范验证
    if re.fullmatch(r'^[0-9\.]+$',address):
        if re.fullmatch(r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',address):
            pass
        else:
            return False,'Invalid address'
    # 否者按照域名规范验证
    elif re.fullmatch(r'^[0-9a-z\-]+\.[0-9a-z\-]+\.[0-9a-z\-]+(\.[0-9a-z\-]+)*$',address):
        pass
    else:
        return False,'Invalid address'
    # 验证端口是否合法
    try:
        int_port=int(port)
    except ValueError:
        return False,'Invalid port'
    else:
        if 0 < int_port < 65536:
            return True,'Valid address'
        else:
            return False,'Invalid port'