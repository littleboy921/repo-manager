import re
import os
from typing import Tuple

current_dir = os.path.dirname(os.path.abspath(__file__))
nginx_conf_file_path=os.path.join(current_dir,"../../nginx.conf")
# 定义函数，获取nginx中对应的端口号
# return: repo_port, api_port
def fetch_nginx_ports() -> Tuple[str, str]:
    with open(nginx_conf_file_path, 'r') as f:
        nginx_conf_content = f.read()
        # 修改找到nginx配置文件中的对应路径的端口号        
        pattern = re.compile(r'.*\nserver\s*{\s*listen\s*(\d+);.*?data-file.*',re.DOTALL)   #re.DOTALL 表示让.可以匹配换行符\n，?表示非贪婪模式，即匹配尽可能少的字符
        repo_port= pattern.sub(r'\1',nginx_conf_content)
        # 修改找到nginx配置文件中的对应路径的端口号        
        pattern = re.compile(r'.*\nserver\s*{\s*listen\s*(\d+);.*?html.*',re.DOTALL)   #re.DOTALL 表示让.可以匹配换行符\n，?表示非贪婪模式，即匹配尽可能少的字符
        api_port= pattern.sub(r'\1',nginx_conf_content)
        return api_port,repo_port