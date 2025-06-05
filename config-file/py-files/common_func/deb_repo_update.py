from flask import current_app
from db_config import pshared_db,repo_update_info_db
from class_define import GlobalVar,DebUpdateInfo
from common_func.to_abs_path import to_abs_path
from typing import List, Tuple
from sqlalchemy import and_
import datetime
import subprocess
import os
import re

# 定义函数，用于deb仓库同步
# args: rela_path: 仓库相对路径，codename：仓库codename
# return：(0,msg) 成功，(1,msg) 失败，(2,msg) 错误
def deb_repo_update(rela_path:str,codename:str)->Tuple[int,str]:
    # 在global_var表中查询全局deb repo update lock锁
    deb_repo_update_lock = pshared_db.query(GlobalVar).filter_by(id='deb_repo_update_lock').first()
    # 假如存在deb repo update lock锁，且该锁的创建时间距当前时间小于24小时（防止意外导锁一直未被删除），则跳过该syncobj的同步
    if deb_repo_update_lock is not None and (datetime.datetime.now() - datetime.datetime.strptime(deb_repo_update_lock.value, '%Y-%m-%d %H:%M:%S')).seconds < 86400:
        current_app.logger.debug(f"Deb repo update lock exist,skip update syncobj deb-repo,{rela_path},{codename}")
        return (1,f"Deb repo update lock exist,skip update syncobj deb-repo,{rela_path},{codename}")
    # 否则，则更新deb repo update lock锁，并继续执行sync job
    # 如果不存在deb repo update lock锁，则创建
    elif deb_repo_update_lock is None:
        new_deb_repo_update_lock = GlobalVar(id='deb_repo_update_lock',value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        pshared_db.add(new_deb_repo_update_lock)
    # 已存在，则更新deb repo update lock锁
    else:
        deb_repo_update_lock.value = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # 将修改提交至数据库
    try:
        pshared_db.commit()
    except Exception as e:
        current_app.logger.error(f"pshared_db commit error,update deb_repo_update_lock failed: {e}")
        pshared_db.rollback()
        # 未能加锁，则跳过该syncobj的同步
        return (1,f"pshared_db commit error,update deb_repo_update_lock failed: {e}")    
    url_rela_path=rela_path
    # 去掉路径开头的/
    if url_rela_path and url_rela_path[0] == '/':
        url_rela_path=url_rela_path[1:]
    # 将rela_path转换为abs_path
    abs_path=to_abs_path(url_rela_path)
    current_app.logger.info(f"Start to update deb-repo,{rela_path},{codename}")
    # 判断log目录是否存在，如果不存在则创建
    log_dir_path=os.path.join(abs_path,"log")
    if not os.path.exists(log_dir_path):
        os.mkdir(log_dir_path)
    # update log日志文件路径
    update_log_file=os.path.join(log_dir_path,"update.log")
    # 将时间戳写入日志
    with open(update_log_file, "a") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Start to checkupdate deb-repo,{rela_path},{codename}\n")
    # 通过popen执行reprepro checkupdate命令更新该仓库，超时时间为4h
    #p = subprocess.Popen(["timeout","4h","reprepro","--noskipold","checkupdate"],bufsize=1,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=abs_path)
    command=f'timeout 4h reprepro --noskipold checkupdate {codename} > updatelist'
    p=subprocess.run(command,shell=True,capture_output=True,text=True,cwd=abs_path)
    returncode = p.returncode
    # 如果从源checkupdate失败，则打印错误信息，并返回
    if returncode != 0:
        with open(update_log_file, "a") as f:
            f.write(f"RETURNCODE:{returncode},deb-repo,{rela_path},{codename} failed to update,error message: {p.stderr}\n")
        current_app.logger.error(f"RETURNCODE:{returncode},deb-repo,{rela_path},{codename} failed to update,error message: {p.stderr}")  
        return (2,f"RETURNCODE:{returncode},deb-repo,{rela_path},{codename} failed to update,error message {p.stderr}")
    # 如果update成功，则打印日志，并删除deb repo update lock锁
    else:
        pshared_db.query(GlobalVar).filter_by(id='deb_repo_update_lock').delete()
        try:
            pshared_db.commit()
        except Exception as e:
            current_app.logger.error(f"pshared_db commit error,delete deb_repo_update_lock failed: {e}")
            pshared_db.rollback()
        # 按行读取updatelist，并将对应的信息填入deb_repo_update_info表中
        with open(os.path.join(abs_path,'updatelist')) as file_r:
            for line in file_r:
                # 处理每一行（自动去除行尾换行符 \n）
                processed_line = line.strip()
                if len(processed_line) == 0:
                    continue
                match = re.search(r"^Updates needed for\s+'(\S+)'",processed_line)
                if match:
                    match_str=match.group(1)
                    match_list=match_str.split('|')
                    codename=match_list[0]
                    component=match_list[1]
                    arch=match_list[2]
                    continue
                match = re.search(r"'(\S+)': newly installed as '\S+' \(from \'(\S+)\'\):",processed_line)
                if match:
                    deb_name=match.group(1)
                    update_conf_name=match.group(2)
                    continue
                match = re.search(r"files needed: (\S+)",processed_line)
                if match:
                    file_rel_path=match.group(1)
                    #deb_update_obj=repo_update_info_db.query(DebUpdateInfo).filter(and_(DebUpdateInfo.))
                    repo_update_info_db.add(DebUpdateInfo(
                        codename=codename,
                        component=component,
                        arch=arch,
                        deb_name=deb_name,
                        update_conf_name=update_conf_name,
                        file_rel_path=file_rel_path
                    ))
                
                    
                    
        return(0,f"deb-repo,{rela_path},{codename} update successfully")
