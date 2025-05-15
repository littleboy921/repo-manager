from db_config import *
from class_define import *
from common_func.get_self_id import get_self_id
from common_func.deb_repo_update import deb_repo_update
from common_func.to_abs_path import to_abs_path
from common_func.create_deb_repo_conf import create_deb_repo_conf
from common_func.fetch_nginx_ports import fetch_nginx_ports
from sqlalchemy import Boolean,Column,Integer,String, DateTime,Boolean,and_,or_,func
import json
import hashlib
import datetime
from flask import Flask,current_app
import subprocess
import os
import threading
import time
import string
import random
import datetime
from multiprocessing import Process, Lock
import requests
import re
import pathvalidate
from typing import List, Tuple

# 进程锁
lock = Lock()
app = Flask(__name__)

# 定义函数：生成bytes string的sha1值
def sha1_bytes(content=None):
    if content is None:
        return ''
    sha1gen = hashlib.sha1()
    sha1gen.update(content)
    sha1code = sha1gen.hexdigest()
    sha1gen = None
    return sha1code

# 定义函数：计算并更新本节点的info_sn值，id一定为本节点的id
def update_info_sn(id)->bool:
    # 获取数据库中本节点信息
    self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=id).first()
    # 构建节点信息列表
    repo_sync_info_list=[]
    # 从数据库获取所有节点信息（除父节点外，包括本节点以及所有未删除的子节点信息）
    for node in repo_sync_info_db.query(RepoSyncInfo).filter(and_(RepoSyncInfo.id!=self_node.parentId,RepoSyncInfo.is_delete==False)):
        # 本节点需要计算的信息
        if node.id == id:
            repo_node_dict={
                'id':node.id,
                'name':node.name,
                'address':node.address,
                'children':node.children,
                'description':node.description
            }
        # 本节点上其他节点需要计算的信息
        else:
            repo_node_dict={
                'id':node.id,
                'name':node.name,
                'address':node.address,
                'children':node.children,
                'description':node.description,
                'parentId':node.parentId,
                'join_time':node.join_time,
                'remote_ip':node.remote_ip
            }
        repo_sync_info_list.append(repo_node_dict)
    # 计算本节点info_sn值
    repo_sync_info_list_json=json.dumps(repo_sync_info_list)
    info_sn_sha1=sha1_bytes(repo_sync_info_list_json.encode('utf-8')) 
    # 获取数据库中本节点信息
    self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=id).first()
    # 更新本节点info_sn值
    self_node.info_sn=info_sn_sha1
    # 写入数据库
    try:
        repo_sync_info_db.commit()
    except Exception as e:
        current_app.logger.error(f"Update info_sn:repo_sync_info_db commit error: {e}")
        repo_sync_info_db.rollback()
        return False
    else:
        current_app.logger.info(f"Update info_sn:repo_sync_info_db commit success")
        return True

# 定义函数：更新数据库中指定id节点的selfnode_info_sn值，这个值计算的是本节点或父节点相关的状态信息，用于父节点通知下级节点本节点的状态变化
# args: id: 节点id(目前仅用于本节点id)
def update_selfnode_info_sn(id:str)->bool:
    # 获取数据库中对应节点信息
    node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=id).first() 
    node_dict={
        'id':id,
        'name':node.name,
        'description':node.description,
    }
    # 获取节点同步对象信息
    syncobj_info_list=[]
    for syncobj in repo_sync_info_db.query(SyncObjInfo).all():
        syncobj_dict={
            'objtype': syncobj.objtype,
            'rela_path': syncobj.rela_path,
            'codename': syncobj.codename,
            'architectures': syncobj.architectures,
            'components': syncobj.components,
            'description':node.description,
            'origin': syncobj.origin
        }
        syncobj_info_list.append(syncobj_dict)
    # 构建节点主要信息数据
    node_info_dict={
        'node_dict': node_dict,
        'syncobj_info_list': syncobj_info_list
    }
    # 计算节点selfnode_info_sn值
    node_info_json=json.dumps(node_info_dict)
    selfnode_info_sn_sha1=sha1_bytes(node_info_json.encode('utf-8')) 
    # 更新节点selfnode_info_sn值
    node.selfnode_info_sn=selfnode_info_sn_sha1
    # 写入数据库
    try:
        repo_sync_info_db.commit()
    except Exception as e:
        current_app.logger.error(f"Update selfnode_info_sn:repo_sync_info_db commit error: {e}")
        repo_sync_info_db.rollback()
        return False
    else:
        current_app.logger.info(f"Update selfnode_info_sn:repo_sync_info_db commit success")
        return True

# 定义函数：将已存在的deb仓库写入到repo_conf_info_db数据库中的deb_repo_info表中
# args: repopath: 仓库路径
def add_new_deb_repo(repopath:str)->Tuple[int,str]:
    # 不允许直接使用/路径
    if repopath == '/':
        return (2,'Cannot add repo with root path!')
    # 去掉repopath开头的/
    if repopath and repopath[0] == '/':
        repopath=repopath[1:]
    # 检查repopath是否为合法路径
    if not pathvalidate.is_valid_filepath(repopath) or re.search(' ', repopath) != None:
        return (1,'Invalid file path') 
    # 将repopath转换为绝对路径
    abs_repo_path=to_abs_path(repopath)
    print(f'abs_repo_path is {abs_repo_path}')
    # 检查abs_repo_path在系统上是否存在，不存在则返回错误
    if not os.path.exists(abs_repo_path):
        current_app.logger.error(f'Repo path not exists in file system! : {abs_repo_path}')
        return (3,'Repo path not exists in file system!')   
    # 读取repo_conf_info_db数据库中的deb_repos表，判断是否已经存在该仓库
    if repo_conf_info_db.query(DebRepoInfo).filter(DebRepoInfo.abs_path == abs_repo_path).first() != None:
        return (4,'Same repo path already added')
    # distributions文件路径
    repo_conf_dist_file=os.path.join(abs_repo_path,"./conf/distributions")
    # 检查distributions文件是否存在
    if not os.path.exists(repo_conf_dist_file):
        return (5,'Repo conf distributions file not exists!')    
    # 执行reprepro sizes 查看仓库信息，获取codename
    p = subprocess.Popen(["reprepro", "sizes"],cwd=abs_repo_path,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        output, errs = p.communicate(timeout=60)  # 仓库信息超时时间设置为1分钟
    except subprocess.TimeoutExpired:
        p.kill()
        output, errs = p.communicate()
    returncode = p.poll()   
    if returncode == 0:
        # 去掉第一行头信息，取出的仓库codename+size信息列表
        distribution_info_list=output.splitlines()[1:]
        for distribution_info in distribution_info_list:
            info_list=re.split(r'\s+',distribution_info)
            codename=info_list[0]
            size=info_list[1]
            # 读取distributions文件中对应codename的配置信息
            with open(repo_conf_dist_file, 'r', encoding='utf-8') as file_r:
                dist_conf_str = file_r.read()
                # 用单独的空行分割配置文件，然后再用正则表达式匹配出对应codename的components、architectures、description信息
                conf_list=re.split(r'\n\n',dist_conf_str)
                for conf_item in conf_list:
                    components_match=re.findall(r'Codename: '+ codename +r'.*Components: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
                    architectures_match=re.findall(r'Codename: '+ codename +r'.*Architectures: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
                    description_match=re.findall(r'Codename: '+ codename +r'.*Description: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
                    #找到第一个匹配即跳出循环，因为codename唯一
                    if components_match != []:
                        break
            # 构造仓库信息字典            
            repo_info_dict={
                'codename': codename,
                'repopath': repopath,
                'abs_path': abs_repo_path,
                'components': components_match[0].strip(),
                'architectures': architectures_match[0].strip(),
                'description': description_match[0].strip(),
                'size': int(size) 
            }
            # 添加到repo_conf_info_db数据库中的deb_repo_info表中
            repo_conf_info_db.add(DebRepoInfo(**repo_info_dict))
        # 将修改提交至数据库
        try:
            repo_conf_info_db.commit()
        except Exception as e:
            return (6,'Failed to add repo to database!'+str(e))
        else:
            return (0,'Success in adding repo to deb repo info db')
    else:
        current_app.logger.error(f'Failed to get repo info by reprepro command! returncode: {returncode}, output: {output}, errs: {errs}')
        return (returncode,'<p>Failed to get repo info by reprepro command!</p>'+errs)  #如果reprepro sizes命令失败，则返回命令错误信息

# 定义函数，将脚本目录添加至syncobj中
def add_script_dir_syncobj(rela_path:str)->Tuple[int,str]:
    # 不允许直接使用/路径
    if rela_path == '/':
        return (2,'Cannot add script dir with root path!')
    # 去掉rela_path开头的/
    if rela_path and rela_path[0] == '/':
        rela_path=rela_path[1:]
    # 检查rela_path是否为合法路径
    if not pathvalidate.is_valid_filepath(rela_path) or re.search(' ', rela_path) != None:
        return (1,'Invalid file path') 
    # 将rela_path转换为绝对路径
    abs_script_dir_path=to_abs_path(rela_path)
    print(f'abs_script_dir_path is {abs_script_dir_path}')
    # 检查abs_script_dir_path在系统上是否存在，不存在则返回错误
    if not os.path.exists(abs_script_dir_path):
        current_app.logger.error(f'Repo path not exists in file system! : {abs_script_dir_path}')
        return (3,'Repo path not exists in file system!')   
    # 读取repo_conf_info_db数据库中的deb_repos表，判断是否已经存在该仓库
    if repo_conf_info_db.query(DebRepoInfo).filter(DebRepoInfo.abs_path == abs_script_dir_path).first() != None:
        return (4,'Same repo path already added')
        
# 周期性刷新节点在线状态，向父节点发送本节点所有在线的节点列表信息作为心跳信号，并且根据父节点返回的info_sn值判断是否需要向父节点更新发送本节点信息，根据父节点返回的is_delete值判断是否需要删除该父节点；父节点返回200，则更新父节点在线信息
# 利用scheduler模块实现周期性任务调度
def heart_beat(self_id,interval=10):
    with app.app_context():
        current_app.logger.debug(f'Heart beat task: pid is {os.getpid()},tid is {threading.get_ident()}')
        # 加锁，防止多个进程同时执行
        with lock:
            # 查询全局时间间隔锁
            heartbeat_interval_lock = pshared_db.query(GlobalVar).filter_by(id='heartbeat_interval_lock').first()
            if heartbeat_interval_lock is not None:
                # 则判断是否到达全局时间间隔，默认为10s，即10秒内不允许重复发送心跳信号
                delta_time = datetime.datetime.now() - datetime.datetime.strptime(heartbeat_interval_lock.value, '%Y-%m-%d %H:%M:%S')
                if delta_time.seconds < interval:
                # 还未达到全局时间间隔，直接返回False
                    current_app.logger.debug(f"Heart beat interval time lock,skip heart beat task")
                    return False
                else:
                    # 已达到全局时间间隔，则更新当前时间间隔锁
                    heartbeat_interval_lock.value = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    try:
                        pshared_db.commit()
                    except Exception as e:
                        current_app.logger.error(f"pshared_db commit error,update heartbeat_interval_lock failed: {e}")
                        pshared_db.rollback()
                        return False
                    else:
                        current_app.logger.debug(f"Update heartbeat_interval_lock success,start heart beat task")
            else:
                # 没有全局时间间隔锁，则创建
                new_interval_lock = GlobalVar(id='heartbeat_interval_lock',value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                pshared_db.add(new_interval_lock)
                try:
                    pshared_db.commit()
                except Exception as e:
                    # 加锁失败，则返回错误信息，并返回False
                    current_app.logger.error(f"pshared_db commit error,add heartbeat_interval_lock failed: {e}")
                    pshared_db.rollback()
                    return False
                else:
                    # 加锁成功，则打印日志，并开始刷新节点在线状态
                    current_app.logger.debug(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}: Add heartbeat_interval_lock success,start heart beat task")
            # 初始化节点在线列表，本节点默认认为自己在线
            online_id_list=[self_id]
            current_app.logger.debug('Start heart beat task')
            # 获取本节点信息
            self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
            # 获取本节点的parentId信息
            parentId=self_node.parentId
            # 如果本节点的parentId不为空，则向父节点的address发送心跳信号，为空则不发送心跳信号
            if parentId:
                # 从数据库获取父节点信息
                parent_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=parentId).first()
                # 从数据库获取父节点address信息
                parent_address=parent_node.address
                # 从数据库获取父节点port信息
                parent_api_port=parent_node.api_port
                # 如果获取父节点地址或端口为空，则返回错误信息
                if parent_address == '' or parent_api_port == '':
                    current_app.logger.error(f'Invalid parent node address message: {parent_address}:{parent_api_port}')
                # 如果是有效父节点信息，则发送心跳信号
                else:
                    # 通过nc命令探测父节点是否可达
                    p = subprocess.Popen(["nc","-w","3","-zv", parent_address,parent_api_port],text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    try:
                        output, errs = p.communicate(timeout=2)  # 探测超时时间为2秒
                    except subprocess.TimeoutExpired:
                        p.kill()
                        output, errs = p.communicate()
                    returncode = p.poll()
                    # 如果父节点不可达，则返回错误信息
                    if returncode != 0:
                        current_app.logger.error(f'Heart beat:failed to connect to parent node: parent_address:{parent_address},parent_api_port:{parent_api_port}')  
                    # 如果父节点可达
                    else:     
                        # 遍历NodeStatus表
                        for node_status in pshared_db.query(NodeStatus).all():
                            # 如果节点在线，且id不等于parentId，则添加到 online_id_list
                            if node_status.check_node_online() and node_status.id != parentId:
                                online_id_list.append(node_status.id)
                        # 向父节点发送本级节点心跳信息
                        try:
                            # 父节点接受心跳信息的api接口地址
                            parent_heartbeat_url=f'http://{parent_address}:{parent_api_port}/remote/child_node_status'
                            # 本节点心跳信息,包含了本节点以及子节点的在线信息
                            health_info={
                                'online_id_list':online_id_list,
                                'auth_code':self_node.parent_auth_code
                            }
                            # 向父节点发送心跳信息
                            timeout = (3, 5)  # (连接超时, 读取超时)
                            response=requests.post(parent_heartbeat_url,json=health_info,timeout=timeout)
                            if response.status_code == 200:
                                current_app.logger.debug(f'Send heart beat to parent node {parent_address}:{parent_api_port} successfully')
                                # 向父节点发送心跳信号成功，则更新pshared_db中父节点的last_update_time
                                node_status=pshared_db.query(NodeStatus).filter_by(id=parentId).first()
                                # 如果父节点状态不存在，则创建
                                if node_status is None:
                                    node_status=NodeStatus(id=parentId)
                                    pshared_db.add(node_status)
                                else:
                                    node_status.update_last_update_time()
                                # 尝试将修改写入数据库
                                try:
                                    pshared_db.commit()
                                except Exception as e:
                                    current_app.logger.error(f"Failed to update child node status:pshared_db commit error: {str(e)}")
                                    pshared_db.rollback()
                                else:
                                    current_app.logger.info(f"Update child node status successfully")
                                # 获取父节点返回的info_sn值
                                response_data = response.json().get('data')
                                parent_save_info_sn= response_data.get('info_sn')
                                current_app.logger.debug(f'send heart beat,parent save info sn : {parent_save_info_sn},self node info sn : {self_node.info_sn}')
                                # 如果父节点返回的info_sn值与本节点的info_sn值不一致，则向父节点发送更新信息
                                if parent_save_info_sn != self_node.info_sn:
                                    current_app.logger.info(f'info_sn not match,need update local info to parent')
                                    send_info_to_parent_node(parent_address,parent_api_port)
                                # 获取父节点返回的selfnode_info_sn值
                                parent_selfnode_info_sn= response_data.get('selfnode_info_sn')
                                save_parent_selfnode_info_sn=parent_node.selfnode_info_sn
                                current_app.logger.debug(f'send heart beat,parent selfnode info sn :{parent_selfnode_info_sn},save parent selfnode info sn :{save_parent_selfnode_info_sn}')
                                # 如果本地存储的父节点selfnode_info_sn值与父节点返回的selfnode_info_sn值不一致，则需要向父节点获取最新信息
                                if parent_selfnode_info_sn != save_parent_selfnode_info_sn:
                                    current_app.logger.info(f'parent selfnode_info_sn not match,need fetch newest info from parent node')
                                    # 向父节点发送获取最新信息的请求
                                    get_sync_object(parent_address,parent_api_port)
                            # 父节点返回403，表明在父节点上，本节点已被删除
                            elif response.status_code == 403:
                                current_app.logger.info(f'Exception in sending heart beat to parent node {parent_address}:{parent_api_port}, error mesg {response.json().get("msg")}')
                                response_data = response.json().get('data')
                                # 验证父节点返回的auth_code
                                auth_code=response_data.get('auth_code')
                                if auth_code != self_node.parent_auth_code:
                                    current_app.logger.error(f'parent node returnauth code not match,do nothing !')
                                # 如果auth_code验证通过，则删除父节点信息
                                else:
                                    # 如果is_delete为true
                                    if response_data.get('is_delete') == 'true':
                                        current_app.logger.info(f'Parent node {parent_address}:{parent_api_port} tell me to delete,delete parent node info')
                                        # 父节点返回is_delete为true，则主动删除父节点信息
                                        # 将本节点sync_obj_info表中非本节点创建的所有同步对象删除（因为非本节点创建的同步对象都是从父节点获取的，所以需要删除）
                                        repo_sync_info_db.query(SyncObjInfo).filter(SyncObjInfo.origin!=self_id).delete()
                                        # 先删除本节点的parentId信息
                                        self_node.parentId=None
                                        # 再删除父节点信息
                                        repo_sync_info_db.delete(parent_node)
                                        # 将修改提交至数据库
                                        try:
                                            repo_sync_info_db.commit()
                                        except Exception as e:
                                            current_app.logger.error(f"repo_sync_info_db commit error,delete parent node info failed: {e}")
                                            repo_sync_info_db.rollback()
                                        else:
                                            # 成功删除父节点信息后，需要更新本节点的selfnode_info_sn值
                                            if update_selfnode_info_sn(self_id):
                                                current_app.logger.info(f"Delete parent node info success")
                                            else:
                                                current_app.logger.error(f"Failed to update selfnode_info_sn")
                            # 其他情况，则打印错误信息
                            else:
                                current_app.logger.error(f'Failed to send heart beat to parent node {parent_address}:{parent_api_port}, response status code:{response.status_code},parent node error mesg {response.json().get("msg")}')
                        except requests.exceptions.RequestException as e:
                                current_app.logger.error(f'Failed to send heart beat to parent node: {str(e)}') 

# 向父节点发送本节点上所有信息，用于更新父节点中本节点信息
def send_info_to_parent_node(parent_address,parent_api_port):
    # 本节点id
    self_id=get_self_id()
    # 父节点地址
    parent_child_update_url=f'http://{parent_address}:{parent_api_port}/remote/update_child_node' 
    # 节点信息列表
    repo_sync_info_list=[]
    # 获取本节点信息
    self_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    # 父节点auth_code
    parent_auth_code=self_node.parent_auth_code 
    # 将本节点信息添加到列表的第一个元素
    repo_sync_info_list.append(self_node.to_dict())
    # 获取其他节点信息,排除父节点信息
    other_nodes = repo_sync_info_db.query(RepoSyncInfo).filter(and_(RepoSyncInfo.id!=self_id,RepoSyncInfo.id!=self_node.parentId)).all()
    # 遍历所有节点信息，将本节点信息添加到列表中
    for node in other_nodes:
        repo_sync_info_list.append(node.to_dict())
    # 发送本节点所有信息给父节点
    try:
        timeout = (3, 5)  # (连接超时, 读取超时)
        response=requests.post(parent_child_update_url,json={'auth_code':parent_auth_code,'repo_sync_info_list':repo_sync_info_list},timeout=timeout)
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f'Cannot send update info to parent node: {str(e)}')
    else:
        if response.status_code == 200:
            current_app.logger.info(f'Send update info to parent node {parent_address}:{parent_api_port} successfully')
        else:
            current_app.logger.error(f'Failed to send update info to parent node {parent_address}:{parent_api_port}, status code {response.status_code},parent node error mesg {response.json().get("msg")}')

# 定义函数： 向父节点获取需要同步的对象，以及父节点相关信息，写入到自身sync_obj_info数据库
def get_sync_object(parent_address,parent_api_port):
    # 本节点id
    self_id = get_self_id()
    # 本节点信息
    self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    # 父节点auth_code
    parent_auth_code = self_node.parent_auth_code
    # 父节点地址
    parent_sync_object_url=f'http://{parent_address}:{parent_api_port}/remote/get_sync_object'
    # 向如节点发送请求，获取需要同步的对象
    try:
        timeout = (3, 5)  # (连接超时, 读取超时)
        response=requests.post(parent_sync_object_url,json={'id':self_id,'auth_code':parent_auth_code},timeout=timeout)
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f'Cannot get sync object from parent node: {str(e)}')
    else:
        if response.status_code == 200:
            current_app.logger.info(f'Get sync object from parent node {parent_address}:{parent_api_port} successfully')
            response_data = response.json().get('data')
            # 获取父节点返回的self_node_dict
            parent_node_dict=response_data.get('self_node_dict')
            # 更新父节点信息
            repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_node.parentId).update(parent_node_dict)
            # 先删除数据库中所有非本节点创建的sync_obj，而后遍历需要同步的对象，写入到数据库中，
            repo_sync_info_db.query(SyncObjInfo).filter(SyncObjInfo.origin!=self_id).delete()
            syncobj_info_list=response_data.get('syncobj_info_list')
            for syncobj in syncobj_info_list:
                # 判断数据库中是否有相同rela_path的对象
                same_rela_path_syncobj=repo_sync_info_db.query(SyncObjInfo).filter_by(rela_path=syncobj['rela_path']).first()
                # 将rela_path转换为abs_path
                abs_path=to_abs_path(syncobj['rela_path'])
                # 判断数据库中是否有相同abs_path的对象
                same_abs_path_syncobj=repo_sync_info_db.query(SyncObjInfo).filter_by(abs_path=abs_path).first()
                # 如果不存在重复对象，则写入数据库，重复的不做处理，这样就允许下级节点创建的同步对象可以覆盖上级节点创建的对象
                if  same_rela_path_syncobj is None and same_abs_path_syncobj is None:
                    # 创建SyncObjInfo对象，注意，不需要设置id，因为id是由本节点数据库自动生成的
                    syncobj_info=SyncObjInfo(
                        objtype=syncobj['objtype'],
                        rela_path=syncobj['rela_path'],
                        abs_path=abs_path,
                        codename=syncobj['codename'],
                        architectures=syncobj['architectures'],
                        components=syncobj['components'],
                        description=syncobj['description'],
                        origin=syncobj['origin']
                    )
                    repo_sync_info_db.add(syncobj_info)
            # 遍历node_sync_obj_status表中node_id等于本节点id的对象，如果不存在于本节点sync_obj_info表中，则删除
            for node_sync_obj_status in pshared_db.query(NodeSyncObjStatus).filter_by(node_id=self_id).all():
                if not repo_sync_info_db.query(SyncObjInfo).filter_by(objtype=node_sync_obj_status.objtype,rela_path=node_sync_obj_status.rela_path,codename=node_sync_obj_status.codename).first():
                    pshared_db.delete(node_sync_obj_status)
            # 尝试将修改提交至数据库
            try:
                repo_sync_info_db.commit()
                pshared_db.commit()
            except Exception as e:
                current_app.logger.error(f"repo_sync_info_db or pshared_dbcommit error, update syncobj object failed: {e}")
                repo_sync_info_db.rollback()
            else:
                # 成功提交后更新本节点的selfnode_info_sn值
                if update_selfnode_info_sn(self_id):
                    current_app.logger.info(f"Fetch and update syncobj successfully!")
                else:
                    current_app.logger.error(f"Fetch syncobj,but failed to update selfnode_info_sn")


# 定义函数：获取本节点的同步对象，请求父节点获取sn值，并和本地sn值进行比对，若不同则对同步对象发起同步请求
def sync_job(self_id,interval=300):
    with app.app_context():
        current_app.logger.debug(f'sync job: pid is {os.getpid()},tid is {threading.get_ident()}')
        # 加锁，防止多个进程同时执行
        with lock:
            # 查询全局时间间隔锁
            syncjob_interval_lock = pshared_db.query(GlobalVar).filter_by(id='syncjob_interval_lock').first()
            if syncjob_interval_lock is not None:
                # 则判断是否到达全局时间间隔，默认为300s，即300秒内不允许重复执行同步任务
                delta_time = datetime.datetime.now() - datetime.datetime.strptime(syncjob_interval_lock.value, '%Y-%m-%d %H:%M:%S')
                if delta_time.seconds < interval:
                # 还未达到全局时间间隔，直接返回False
                    current_app.logger.debug(f"Heart beat interval time lock,skip heart beat task")
                    return False
                else:
                    # 已达到全局时间间隔，则更新当前时间间隔锁
                    syncjob_interval_lock.value = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    try:
                        pshared_db.commit()
                    except Exception as e:
                        current_app.logger.error(f"pshared_db commit error,update syncjob_interval_lock failed: {e}")
                        pshared_db.rollback()
                        return False
                    else:
                        current_app.logger.debug(f"Update syncjob_interval_lock success,start heart beat task")
            else:
                # 没有全局时间间隔锁，则创建
                new_interval_lock = GlobalVar(id='syncjob_interval_lock',value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                pshared_db.add(new_interval_lock)
                try:
                    pshared_db.commit()
                except Exception as e:
                    # 加锁失败，则返回错误信息，并返回False
                    current_app.logger.error(f"pshared_db commit error,add syncjob_interval_lock failed: {e}")
                    pshared_db.rollback()
                    return False
                else:
                    # 加锁成功，则打印日志，并开始刷新节点在线状态
                    current_app.logger.debug(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}: Add syncjob_interval_lock success,start heart beat task")
            # 查询本节点信息
            self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
            # 如果parentId不存在，则打印日志，并退出
            if self_node.parentId is None:
                current_app.logger.info(f"Parent node not exist,skip sync job")
                return False
            else:
                # 获取父节点信息
                parent_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_node.parentId).first()
            # 获取父节点address
            parent_address=parent_node.address
            # 获取父节点api_port
            parent_api_port=parent_node.api_port
            # 获取父节点repo_port
            parent_repo_port=parent_node.repo_port
            # 父节点syncobj sn 信息获取 url
            parent_sn_url=f'http://{parent_address}:{parent_api_port}/remote/get_syncobj_sn'
            # 构建请求信息
            post_syncobj_list=[]
            # 从数据库获取所有非本节点创建的sync_obj，向父节校验sn值，父节点会返回sn不同的syncobj列表，而后对此列表中的syncobj发起同步请求
            for syncobj in repo_sync_info_db.query(SyncObjInfo).filter(SyncObjInfo.origin!=self_id).all():                
                # 向post_syncobj_list中添加syncobj信息
                post_syncobj_list.append(
                    {
                        'objtype':syncobj.objtype,
                        'rela_path':syncobj.rela_path,
                        'codename':syncobj.codename,
                        'sn':syncobj.sn
                    },
                )
            # 向父节点发送请求，获取syncobj sn信息
            try:
                timeout = (3, 5)  # (连接超时, 读取超时)
                response=requests.post(parent_sn_url,json={'id':self_id,'auth_code':parent_node.auth_code,'syncobj_list':post_syncobj_list},timeout=timeout)
            except requests.exceptions.RequestException as e:
                # 若请求失败，则打印日志
                current_app.logger.error(f'Cannot get syncobj sn from parent node: {str(e)}')
            else:
                if response.status_code == 200:
                    # 获取父节点返回的need_sync_syncobj_list，其中都是未同步的syncobj
                    need_sync_syncobj_list=response.json().get('data').get('need_sync_syncobj_list')
                    # 获取父节点返回的synced_syncobj_list，其中都是已同步的syncobj
                    synced_syncobj_list=response.json().get('data').get('synced_syncobj_list')
                    # 打印日志
                    current_app.logger.debug(f"Need to sync from parent node {parent_address}:{parent_repo_port},need_sync_syncobj_list is {need_sync_syncobj_list},synced_syncobj_list is {synced_syncobj_list}")
                    # 遍历父节点返回的synced_syncobj_list，更新node_sync_obj_status表中的对应syncobj状态信息，将status设置为True，表明处于同步状态
                    for syncobj in synced_syncobj_list:
                        # 在node_sync_obj_status表进行记录，status为 True表明当前该syncobj 处于已同步状态
                        node_sync_obj_status=pshared_db.query(NodeSyncObjStatus).filter_by(node_id=self_id,objtype=syncobj['objtype'],rela_path=syncobj['rela_path'],codename=syncobj['codename']).first()
                        if node_sync_obj_status is None:
                            new_node_sync_obj_status=NodeSyncObjStatus(node_id=self_id,objtype=syncobj['objtype'],rela_path=syncobj['rela_path'],codename=syncobj['codename'],status=True)
                            pshared_db.add(new_node_sync_obj_status)
                        else:
                            node_sync_obj_status.status=True
                        try:
                            pshared_db.commit()
                        except Exception as e:
                            current_app.logger.error(f"pshared_db commit error,update node_sync_obj_status {syncobj['objtype']},{syncobj['rela_path']},{syncobj['codename']} status to True failed: {e}")
                            pshared_db.rollback()
                        else:
                            current_app.logger.debug(f"Update node_sync_obj_status {syncobj['objtype']},{syncobj['rela_path']},{syncobj['codename']} status to True success")
                    # 如果need_sync_syncobj_list为空，表明所有syncobj都已同步，则打印日志，并退出
                    if len(need_sync_syncobj_list) == 0:
                        current_app.logger.debug(f"All syncobj is synchronized")
                        return True
                    # 遍历父节点返回的need_sync_syncobj_list，更新本地数据库中syncobj，将status设置为False，表明处于未同步状态
                    for syncobj in need_sync_syncobj_list:
                        # 在node_sync_obj_status表进行记录，将status设置为False，表明当前该syncobj 处于未同步状态
                        node_sync_obj_status=pshared_db.query(NodeSyncObjStatus).filter_by(node_id=self_id,objtype=syncobj['objtype'],rela_path=syncobj['rela_path'],codename=syncobj['codename']).first()
                        if node_sync_obj_status is None:
                            new_node_sync_obj_status=NodeSyncObjStatus(node_id=self_id,objtype=syncobj['objtype'],rela_path=syncobj['rela_path'],codename=syncobj['codename'],status=False)
                            pshared_db.add(new_node_sync_obj_status)
                        else:
                            node_sync_obj_status.status=False
                        try:
                            pshared_db.commit()
                        except Exception as e:
                            current_app.logger.error(f"pshared_db commit error,update node_sync_obj_status {syncobj['objtype']},{syncobj['rela_path']},{syncobj['codename']} failed: {e}")
                            pshared_db.rollback()
                        else:
                            current_app.logger.debug(f"Update node_sync_obj_status {syncobj['objtype']},{syncobj['rela_path']},{syncobj['codename']} success")
                        # 区分不同类型的同步对象，并调用相应的同步方法
                        if syncobj['objtype'] == 'deb-repo':
                            # 从sync_obj_info数据库获取该deb-repo类型的syncobj相关信息
                            sync_obj_info=repo_sync_info_db.query(SyncObjInfo).filter(and_(SyncObjInfo.origin!=self_id,SyncObjInfo.objtype=='deb-repo',SyncObjInfo.rela_path==syncobj['rela_path'],SyncObjInfo.codename==syncobj['codename'])).first()
                            # 构建distributions配置数据
                            distributions_conf_data={
                                'codename':sync_obj_info.codename,
                                'update':sync_obj_info.origin,
                                'architectures':sync_obj_info.architectures,
                                'components':sync_obj_info.components,
                                'description':sync_obj_info.description
                            }
                            # 构建update请求url，syncobj中的deb-repo，上游源地址为父节点的ip地址
                            upstream_ipaddress=parent_address
                            upstream_port=parent_repo_port 
                            update_url=f"http://{upstream_ipaddress}:{upstream_port}/{syncobj['rela_path']}"
                            # 构建update配置数据
                            update_conf_data={
                                'name':sync_obj_info.origin,
                                'suite':sync_obj_info.codename,
                                'architectures':sync_obj_info.architectures,
                                'components':sync_obj_info.components,
                                'method':update_url
                            }
                            # 调用create_deb_repo_conf函数，生成deb repo配置文件，如果生成失败，则打印日志，并退出
                            if not create_deb_repo_conf(to_abs_path(sync_obj_info.rela_path),distributions_conf_data,update_conf_data):
                                current_app.logger.error(f"Create deb repo config file failed,skip sync job:update {syncobj['objtype']},{syncobj['rela_path']},{syncobj['codename']}")
                                return False
                            # 调用deb_repo_update函数，更新本地仓库
                            update_result = deb_repo_update(syncobj['rela_path'],syncobj['codename'])
                            if update_result[0] != 0:
                                current_app.logger.error(update_result[1])  
                            # 如果update成功，则打印日志，并更新数据库中syncobj的sn值，将node_sync_obj_status表中status置为True
                            else:   
                                sync_obj_info.sn=syncobj['sn']
                                pshared_db.query(NodeSyncObjStatus).filter_by(node_id=self_id,objtype=syncobj['objtype'],rela_path=syncobj['rela_path'],codename=syncobj['codename']).update({'status':True})
                                try:
                                    pshared_db.commit()
                                    repo_sync_info_db.commit()
                                except Exception as e:
                                    current_app.logger.error(f"repo_sync_info_db or pshared_db commit error,update syncobj sn {syncobj['objtype']},{syncobj['rela_path']},{syncobj['codename']} failed: {str(e)}")
                                    pshared_db.rollback()
                                else:
                                    current_app.logger.info(f"{syncobj['objtype']},{syncobj['rela_path']},{syncobj['codename']} update from source {parent_address} successfully")
                        # 如果同步对象类型为script-dir
                        if syncobj['objtype'] == 'script-dir':
                            # 从sync_obj_info数据库获取该script-dir类型的syncobj相关信息，注意origin为非本节点id，即并不对本节点创建的script-dir进行同步
                            sync_obj_info=repo_sync_info_db.query(SyncObjInfo).filter(and_(SyncObjInfo.origin!=self_id,SyncObjInfo.objtype=='script-dir',SyncObjInfo.rela_path==syncobj['rela_path'])).first()
                            # 构建update请求url，syncobj中的script-dir，上游源地址为父节点的address+repo_port
                            remote_git_repo=f"http://{parent_address}:{parent_repo_port}/git/{syncobj['rela_path']}"
                            # 将syncobj['rela_path']转化为本地绝对路径
                            local_abs_path=to_abs_path(syncobj['rela_path'])
                            # 如果本地目录不存在，则创建对应的目录后拉取
                            if not os.path.exists(local_abs_path):
                                repo_parent_dir=os.path.dirname(local_abs_path)
                                # 通过git clone命令拉取远程仓库
                                # 通过popen执行git脚本初始化该仓库，超时时间为1h
                                p = subprocess.Popen(["timeout","1h","git",'clone',remote_git_repo],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=repo_parent_dir)
                                # 尝试读取子进程的返回值，超时时间为60s
                                try:
                                    output, errs = p.communicate(timeout=60)
                                except subprocess.TimeoutExpired as e:
                                    p.kill()
                                    output, errs = p.communicate()
                                    current_app.logger.error(f"p.communicate timeout, err:{str(e)}")
                                returncode = p.poll()
                                # 如果从源clone失败，则打印错误信息，并返回
                                if returncode != 0:
                                    current_app.logger.error(f"RETURNCODE:{returncode},failed to git clone repo {remote_git_repo}: output:{output.decode('utf-8')},error:{errs.decode('utf-8')}")  
                                    return False
                                # 如果clone成功，则打印日志，并更新数据库中syncobj的sn值，将node_sync_obj_status表中status置为True
                                else:
                                    sync_obj_info.sn=syncobj['sn']
                                    pshared_db.query(NodeSyncObjStatus).filter_by(node_id=self_id,objtype=syncobj['objtype'],rela_path=syncobj['rela_path']).update({'status':True})
                                    try:
                                        pshared_db.commit()
                                        repo_sync_info_db.commit()
                                    except Exception as e:
                                        current_app.logger.error(f"repo_sync_info_db or pshared_db commit error,update syncobj sn {syncobj['objtype']},{syncobj['rela_path']} failed: {str(e)}")
                                        pshared_db.rollback()
                                    else:                                  
                                        current_app.logger.info(f"{syncobj['objtype']},{syncobj['rela_path']},Clone git repo {remote_git_repo} successfully")
                                    return True
                            elif os.path.exists(os.path.join(local_abs_path,".git")):
                                # 如果本地目录中存在.git目录，则通过git pull命令更新本地仓库
                                # 通过popen执行git脚本更新该仓库，超时时间为1h
                                p = subprocess.Popen(["timeout","1h","git","pull"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=local_abs_path)
                                # 尝试读取子进程的返回值，超时时间为60s
                                try:
                                    output, errs = p.communicate(timeout=60)   
                                except subprocess.TimeoutExpired as e:
                                    p.kill()
                                    output, errs = p.communicate()
                                    current_app.logger.error(f"p.communicate timeout, err:{str(e)}")
                                returncode = p.poll()
                                # 如果从源pull失败，则打印错误信息，并返回
                                if returncode != 0:
                                    current_app.logger.error(f"RETURNCODE:{returncode},failed to git pull repo {remote_git_repo}: output:{output.decode('utf-8')},error:{errs.decode('utf-8')}")  
                                    return False
                                # 如果pull成功，则打印日志，并更新数据库中syncobj的sn值，将node_sync_obj_status表中status置为True
                                else:
                                    sync_obj_info.sn=syncobj['sn']
                                    pshared_db.query(NodeSyncObjStatus).filter_by(node_id=self_id,objtype=syncobj['objtype'],rela_path=syncobj['rela_path']).update({'status':True})
                                    try:
                                        pshared_db.commit()
                                        repo_sync_info_db.commit()
                                    except Exception as e:
                                        current_app.logger.error(f"repo_sync_info_db or pshared_db commit error,update syncobj sn {syncobj['objtype']},{syncobj['rela_path']} failed: {str(e)}")
                                        pshared_db.rollback()
                                    else:
                                        current_app.logger.info(f"{syncobj['objtype']},{syncobj['rela_path']},Pull git repo {remote_git_repo} successfully")
                                    return True
