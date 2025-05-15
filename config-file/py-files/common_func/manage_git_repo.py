from common_func.to_abs_path import to_abs_path
from flask import current_app
import subprocess
import datetime
import os
from typing import Tuple

# 当前脚本文件绝对路径目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# git仓库初始化脚本路径
manage_git_script = os.path.join(current_dir,'../../sh-scripts/manage_git_repo.sh')

# 定义函数，创建git仓库，并将信息写入同步对象数据库
def create_git_repo(rela_path:str)->Tuple[bool,str]:
    # 去掉路径开头的/
    if rela_path and rela_path[0] == '/':
        rela_path=rela_path[1:]
    # 转换为绝对路径
    abs_path = to_abs_path(rela_path)
    # 判断路径是否存在，不存在则返回错误信息
    if not os.path.exists(abs_path):
        return False,f"Path {abs_path} doesn't exist."
    # 通过git命令创建仓库
    # 通过popen执行git脚本初始化该仓库，超时时间为1h
    p = subprocess.Popen(["timeout","1h","/bin/bash",manage_git_script,'init'],bufsize=1,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=abs_path)
    # 尝试读取子进程的返回值，超时时间为60s
    try:
        output, errs = p.communicate(timeout=60)
    except subprocess.TimeoutExpired as e:
        p.kill()
        output, errs = p.communicate()
        current_app.logger.error(f"p.communicate timeout, err:{str(e)}")
    returncode = p.poll()
    # 如果创建失败，则打印错误信息，并返回
    if returncode != 0:
        current_app.logger.error(f"RETURNCODE:{returncode},{rela_path} failed to create git repo message: output:{output.decode('utf-8')},error:{errs.decode('utf-8')}")  
        return False,f"RETURNCODE:{returncode},{rela_path},failed to create git repo,output:{output.decode('utf-8')},error:{errs.decode('utf-8')}"
    # 如果创建成功，则打印日志
    else:
        return True,f"{rela_path},git repo create successfully"
    
# 定义函数，对git仓库执行commit操作，并将信息从同步对象数据库中删除
# args: abs_path: 仓库绝对路径
def commit_git_repo(abs_path:str)->Tuple[bool,str]:
    # 通过popen执行git脚本commit该仓库，超时时间为1h
    p = subprocess.Popen(["timeout","1h","/bin/bash",manage_git_script,'commit'],bufsize=1,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=abs_path)
    # 尝试读取子进程的返回值，超时时间为60s
    try:
        output, errs = p.communicate(timeout=60)
    except subprocess.TimeoutExpired as e:
        p.kill()
        output, errs = p.communicate()
        current_app.logger.error(f"p.communicate timeout, err:{str(e)}")
        return False,f"p.communicate timeout, err:{str(e)}"
    returncode = p.poll()
    # 如果执行失败，则打印错误信息，并返回失败信息
    if returncode != 0:
        current_app.logger.error(f"RETURNCODE:{returncode},{abs_path} failed to git commit,output:{output.decode('utf-8')},error:{errs.decode('utf-8')}")
        return False,f"RETURNCODE:{returncode},{abs_path},failed to git commit,output:{output.decode('utf-8')},error:{errs.decode('utf-8')}"
    # 如果执行成功，打印日志
    else:
        current_app.logger.info(f"receive_file: {abs_path} saved successfully, git commit successfully!")
        return True,f"{abs_path},git commit update successfully"
      