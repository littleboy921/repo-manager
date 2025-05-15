from db_config import *
from func_define import *
from class_define import *
from common_func.get_self_id import get_self_id
from common_func.is_valid_address_port import is_valid_address_port
from common_func.manage_git_repo import create_git_repo,commit_git_repo

from flask import Flask,request,jsonify,Blueprint,send_file,render_template,current_app
from sqlalchemy import and_,or_,func
import os, time
import subprocess
import re
import requests
import json
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
import yaml

# 创建蓝图对象
sync_repo_api=Blueprint('sync_repo_api',__name__)
app = Flask(__name__)
#设置正确的时区
os.environ['TZ'] = 'Asia/Shanghai'
time.tzset()

# 当前脚本文件绝对路径目录
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_config_file = os.path.join(current_dir,"repo-manager-conf.yml")

# 全局变量self_id，用于标识本节点的id
self_id = get_self_id()

# 获取本节点信息，以及父节点信息，用于渲染相关页面元素(不带status信息)
@sync_repo_api.route('/get_self_node_info',methods=['GET'])
def get_self_node_info():
    global self_id
    self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    parentId=self_node.parentId
    self_info_dict={
                    'id': self_node.id,
                    'name': self_node.name,
                    'address': self_node.address,
                    'api_port': self_node.api_port,
                    'repo_port': self_node.repo_port,
                    'description': self_node.description,
                    'auth_code': self_node.auth_code,
                    }
    # 如果存在父节点，则获取父节点信息
    if parentId:
        parent_info_dict=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=parentId).first().to_dict_with_status()
    else:
        parent_info_dict=None
    current_app.logger.debug(f'self node info:{self_info_dict}, parent node info:{parent_info_dict}')
    return jsonify({'code':0,'msg':'success','data':{'self_info_dict':self_info_dict,'parent_info_dict':parent_info_dict}})

# 将页面信息提交给后端，更新本节点仓库信息
@sync_repo_api.route('/update_self_node_info',methods=['POST'])
def update_self_node_info():
    global self_id
    # 获取本节点信息
    self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    #获取post请求data
    post_data=request.json  #将json格式的请求数据转换为字典
    # 验证提交的地址数据是否合法
    address=post_data['self-address']
    api_port=post_data['self-api-port']
    repo_port=post_data['self-repo-port']
    check_result1=is_valid_address_port(address,api_port)
    check_result2=is_valid_address_port(address,repo_port)
    if not check_result1[0] or not check_result2[0]:  # 如果地址校验不通过，则返回报错信息
        current_app.logger.error(f"Invalid self node address: {address}, {api_port}, {repo_port}")
        return jsonify({'code':1,'msg':f"Invalid self node address: {address},{api_port},{repo_port},{check_result1[1]},{check_result2[1]}"}),400
    # 在数据库查找，是否存在同名节点，不允许修改为重名
    same_name_node=repo_sync_info_db.query(RepoSyncInfo).filter(and_(RepoSyncInfo.name==post_data['self-name'],RepoSyncInfo.is_delete==False),RepoSyncInfo.id!=self_id).first()
    if same_name_node:
        current_app.logger.error(f"Failed to update self node info, same name node exist")
        return jsonify({'code':1,'msg':'Failed to update self node info, same name node exist'})
    if self_node.parentId:
        parent_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_node.parentId).first()
        if not parent_node:  # 如果父节点不存在，则在日志记录错误
            current_app.logger.error(f"Failed to update self node info, cannot find parent node from database")
        # 如果存在父节点，则需要向父节点发送本节点信息，确保整个树结构中没有重名节点
        parent_address=parent_node.address
        parent_api_port=parent_node.api_port
        parent_auth_code=parent_node.auth_code
        # 获取post提交的数据，并发送给父节点
        parent_child_update_url=f'http://{parent_address}:{parent_api_port}/remote/update_child_node'
        update_info_list=[{
            'id': self_id,
            'name': post_data['self-name'],
            'address': post_data['self-address'],
            'children': json.loads(self_node.children),
            'description': post_data['self-description'],
            'info_sn': self_node.info_sn
            }] 
        try:
            timeout = (3, 5)  # (连接超时, 读取超时)
            response=requests.post(parent_child_update_url,json={'auth_code':parent_auth_code,'repo_sync_info_list':update_info_list},timeout=timeout)
            response_data=response.json()
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f'Cannot send update info to parent node,{e}')
            return jsonify({'code':1,'msg':f"Failed to send update info to parent node,{e}"}),401
        except requests.exceptions.JSONDecodeError as e:
            current_app.logger.error(f"Failed to send update info to parent node,response code {response.status_code},JSONDecodeError: {e}")
            return jsonify({'code':1,'msg':f"Failed to send update info to parent node,response code {response.status_code},JSONDecodeError: {e}"})
        else:
            if response.status_code == 200:
                current_app.logger.info(f'Send update info to parent node {parent_address}:{parent_api_port} successfully')
            else:
                current_app.logger.error(f'Failed to send update info to parent node {parent_address}:{parent_api_port}, response code {response.status_code},parent node error mesg {response_data.get("msg")}')
                return jsonify({'code':1,'msg':f"Send update info to parent node error: {response_data.get('msg')}"})
    # 将post提交的数据填入到self_node中
    repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).update({'name':post_data['self-name'],'address':post_data['self-address'],'api_port':post_data['self-api-port'],'repo_port':post_data['self-repo-port'],'description':post_data['self-description']},synchronize_session=False)
    # 写入到数据库
    try:
        repo_sync_info_db.commit()
    except Exception as e:
        current_app.logger.error(f"repo_sync_info_db commit error: {e}")
        repo_sync_info_db.rollback()
        return jsonify({'code':1,'msg':'Failed to update self node info'})
    else:
        current_app.logger.info(f"Update self node info successfully")
        # 更新本节点info_sn值，以及selfnode_info_sn值
        if update_info_sn(self_id):
            if update_selfnode_info_sn(self_id):
                return jsonify({'code':0,'msg':'Success in updating info_sn and selfnode_info_sn'})
            else:
                current_app.logger.error(f"Failed to update selfnode_info_sn")
                return jsonify({'code':1,'msg':'Failed to update selfnode_info_sn'})
        else:
            current_app.logger.error(f"Failed to update info_sn")
            return jsonify({'code':1,'msg':'Failed to update info_sn'})
    
# 修改父节点信息(只允许修改父节点address以及api_port、repo_port)
@sync_repo_api.route('/update_parent_node_info',methods=['POST'])
def update_parent_node_info():
    global self_id
    # 获取本节点信息
    self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    # 获取父节点信息
    parent_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_node.parentId).first()
    # 获取post请求data
    post_data=request.json  #将json格式的请求数据转换为字典
    # 获取提交的父节点地址
    parent_address=post_data.get('parent_address')
    # 获取提交的父节点api_port
    parent_api_port=post_data.get('parent_api_port')
    # 获取提交的父节点repo_port
    parent_repo_port=post_data.get('parent_repo_port')
    # 如果提交的是parent_address
    if parent_address:
        check_result=is_valid_address_port(address=parent_address)
        if not check_result[0]:  # 如果地址校验不通过，则返回报错信息
            current_app.logger.error(f"Invalid parent node address: {parent_address}")
            return jsonify({'code':1,'msg':f"Invalid parent node address: {parent_address},{check_result[1]}"}),400
        else:
            # 将修改提交至数据库
            try:
                parent_node.address=parent_address
                repo_sync_info_db.commit()
            except Exception as e:
                current_app.logger.error(f"Failed to update parent node address, {str(e)}")
                repo_sync_info_db.rollback()
                return jsonify({'code':1,'msg':'Failed to update parent node address'}),400
            else:
                current_app.logger.info(f"Update parent node address successfully, parent node address: {parent_address}")
                return jsonify({'code':0,'msg':'Success in updating parent node address'})
    # 如果提交的是parent_api_port
    elif parent_api_port:
        # 验证提交的端口是否合法
        check_result=is_valid_address_port(port=parent_api_port)
        if not check_result[0]:  # 如果地址校验不通过，则返回报错信息
            current_app.logger.error(f"Invalid parent node api_port: {parent_api_port}")
            return jsonify({'code':1,'msg':f"Invalid parent_api_port: {parent_api_port},{check_result[1]}"}),400
        else:
            # 将修改提交至数据库
            try:
                parent_node.api_port=parent_api_port
                repo_sync_info_db.commit()
            except Exception as e:
                current_app.logger.error(f"Failed to update parent_api_port, {str(e)}")
                repo_sync_info_db.rollback()
                return jsonify({'code':1,'msg':'Failed to update parent_api_port'}),400
            else:
                current_app.logger.info(f"Update parent_api_port successfully, parent_api_port: {parent_api_port}")
                return jsonify({'code':0,'msg':'Success in updating parent_api_port'})
    # 如果提交的是parent_repo_port
    elif parent_repo_port:
        # 验证提交的端口是否合法
        check_result=is_valid_address_port(port=parent_repo_port)
        if not check_result[0]:  # 如果地址校验不通过，则返回报错信息
            current_app.logger.error(f"Invalid parent node repo_port: {parent_repo_port}")
            return jsonify({'code':1,'msg':f"Invalid parent_repo_port: {parent_repo_port},{check_result[1]}"}),400
        else:
            # 将修改提交至数据库
            try:
                parent_node.repo_port=parent_repo_port
                repo_sync_info_db.commit()
            except Exception as e:
                current_app.logger.error(f"Failed to update parent_repo_port, {str(e)}")
                repo_sync_info_db.rollback()
                return jsonify({'code':1,'msg':'Failed to update parent_repo_port'}),400
            else:
                current_app.logger.info(f"Update parent_repo_port successfully, parent_repo_port: {parent_repo_port}")
                return jsonify({'code':0,'msg':'Success in updating parent_repo_port'})
    # 如果提交的字段不在上述三个中，则返回报错信息
    else:
        current_app.logger.error(f"Invalid parent node info update field")
        return jsonify({'code':1,'msg':'Invalid parent node info update field'}),400
                               
# 从配置文件获取所有节点同步结构信息，用于渲染树形表格，含status信息
@sync_repo_api.route('/get_repo_sync_info',methods=['GET'])
def get_repo_sync_info():
    global self_id
    self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    # 构建节点信息列表，第一个元素为本节点信息
    repo_sync_info_list=[self_node.to_dict_with_status()]    
    # 从数据库获取除本节点、父节点以外的所有未删除的节点信息
    for node in repo_sync_info_db.query(RepoSyncInfo).filter(and_(RepoSyncInfo.id!=self_node.parentId,RepoSyncInfo.id!=self_id,RepoSyncInfo.is_delete==False)).all():
        repo_sync_info_list.append(node.to_dict_with_status())
    return jsonify({'code':0,'msg':'success','data':repo_sync_info_list})

# 添加父节点页面api入口
@sync_repo_api.route('/add_parent_node',methods=['POST'])
def add_parent_node():
    global self_id
    #获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典
    # 获取父节点address
    parent_address=post_data['parent-address']
    # 获取父节点api_port
    parent_api_port=post_data['parent-api-port']
    # 获取父节点认证码
    parent_auth_code=post_data['parent-auth-code']
    check_result=is_valid_address_port(parent_address,parent_api_port)
    if not check_result[0]:  # 如果地址校验不通过，则返回报错信息
        current_app.logger.error(f'Invalid parent node address message:{parent_address}:{parent_api_port}')
        return jsonify({'code':1,'msg':'Invalid parent node address message'})
    
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
        current_app.logger.error(f'Failed to connect to parent node: address:{parent_address},port:{parent_api_port}')
        return jsonify({'code':1,'msg':'Failed to connect to parent node, parent node unreacheable'})    
    # 父节点可达
    else:
        current_app.logger.debug(f'Successfully nc to parent node: address:{parent_address},port:{parent_api_port}')
        # 父节点添加子节点api接口地址
        parent_url = f"http://{parent_address}:{parent_api_port}/remote/add_child_node"
        # 构建repo_sync_info列表
        repo_sync_info_list=[]
        # 从数据库获取本节点信息
        self_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
        # 将本节点信息添加到repo_sync_info_list列表第一个元素
        repo_sync_info_list.append(self_node.to_dict())
        # 从数据库获取其他所有未删除的节点信息
        for node in repo_sync_info_db.query(RepoSyncInfo).filter(and_(RepoSyncInfo.id!=self_id,RepoSyncInfo.is_delete==False)).all():
            repo_sync_info_list.append(node.to_dict())
        # 向获取父节点发送加入请求，如果成功则将父节点相关信息填入本节点中       
        try:
            # 给父节点发送请求，附带parent_auth_code和所有节点的信息列表
            response = requests.post(parent_url, json={'auth_code':parent_auth_code,'repo_sync_info_list':repo_sync_info_list})            
            # 检查响应状态码
            # 如果为200，则父节点添加成功，将父节点id信息写入到本节点id中，并添加父节点数据记录,将前端填写的parent_address信息写入
            if response.status_code == 200:
                # 获取response返回信息
                response_data = response.json().get('data')
                # 获取父节点名称
                parent_info_dict = response_data.get('parent_info_dict')
                # 将父节点id写入本节点parentId中
                self_node.parentId=parent_info_dict['id']
                # 将父节点auth_code写入本节点parent_auth_code中
                self_node.parent_auth_code=parent_auth_code
                # 如果父节点已存在于数据库中，则报错
                if repo_sync_info_db.query(RepoSyncInfo).filter_by(id=parent_info_dict['id']).first():
                    current_app.logger.error(f"Failed to add parent node,parent node id:{parent_info_dict['id']} already exist")
                    return jsonify({'code':1,'msg':f"Failed to add parent node,parent node id:{parent_info_dict['id']} already exist"})
                # 增加父节点数据记录，注意将前端填写的parent_address,parent_auth_code信息写入数据库中父节点的address字段
                # 注意，这里并不填入父节点的selfnode_info_sn字段，这个字段等下一个心跳信号到来时自动更新
                parent_node_info=RepoSyncInfo(
                    id=parent_info_dict['id'],
                    name=parent_info_dict['name'],
                    address=parent_address,
                    api_port=parent_info_dict['api_port'],
                    repo_port=parent_info_dict['repo_port'],
                    auth_code = parent_auth_code,
                    children=json.dumps(parent_info_dict['children']),
                    description=parent_info_dict['description'],
                )
                repo_sync_info_db.add(parent_node_info)
                # 提交修改至数据库中
                try:
                    repo_sync_info_db.commit()
                except Exception as e:
                    current_app.logger.error(f"Failed to add parent address:{parent_address},auth_code:{parent_auth_code},repo_sync_info_db commit error: {str(e)}")
                    repo_sync_info_db.rollback()
                    return jsonify({'code':1,'msg':f"Failed to add parent node,address:{parent_address}"})
                else:
                    current_app.logger.info(f"Add parent node name:{parent_info_dict['name']},address:{parent_address} successfully")
                    return jsonify({'code':0,'msg':f"Success in adding parent node name:{parent_info_dict['name']}"})
            else:
                repo_sync_info_db.rollback()
                current_app.logger.error(f'Add parent address:{parent_address} request failed with status code {response.status_code}')
                return jsonify({'code':2,'msg':f"Request failed,Parent node:{parent_address} {response.json().get('msg')}"})
        except requests.exceptions.RequestException as e:    # requests.exceptions.RequestException是requests库中所有异常的基类
            current_app.logger.error(f'Cannot send join request to parent address:{parent_address}:{str(e)}')
            repo_sync_info_db.rollback()
            return jsonify({'code':3,'msg':f'Cannot send join request to parent node:{str(e)}'})

# 删除父节点
@sync_repo_api.route('/delete_parent_node',methods=['POST'])
def delete_parent_node():
    global self_id
    # 获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典
    # 获取删除模式，0为正常删除（必需成功通知上级节点），1为强制删除
    delete_mode=post_data['delete_mode']
    # 获取本节点信息
    self_node_info=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    # 如果本节点没有父节点，则返回错误信息
    if not self_node_info.parentId:
        current_app.logger.error(f"Failed to delete parent node,self node has no parent node")
        return jsonify({'code':1,'msg':'Failed to delete parent node,self node has no parent node'})
    # 获取父节点信息
    else:
        parent_node_info=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_node_info.parentId).first()
        parent_url = 'http://'+parent_node_info.address+'/remote/delete_child_node'
        try:
            # 向父节点发送删除子节点请求
            timeout = (3, 5)  # (连接超时, 读取超时)
            response = requests.post(parent_url, json={'id':self_id,'auth_code':parent_node_info.auth_code},timeout=timeout)
        except requests.exceptions.RequestException as e:
            # 如果无法连接到父节点，则记录错误信息
            current_app.logger.error(f'Cannot send delete request to parent node {parent_node_info.name},address:{parent_node_info.address}, err msg:{str(e)}')
            # 如果删除模式为正常删除，则返回错误信息并退出,否则继续执行后续操作
            if delete_mode == 0:
                return jsonify({'code':1,'msg':f'Cannot send delete request to parent node {parent_node_info.name},address:{parent_node_info.address}, err msg:{str(e)}'})
        else:
            # 检查子父节点响应状态码
            if response.status_code == 200:
                current_app.logger.info(f"Ask parent node name:{parent_node_info.name},address:{parent_node_info.address} to delete child node successfully")
            else:
                # 其他状态码
                try:
                    err_msg= response.json().get('msg')
                except Exception as e:
                    err_msg=str(e)
                current_app.logger.error(f"Ask parent node name:{parent_node_info.name},address:{parent_node_info.address} to delete child node response status code: {response.status_code},error mesg {err_msg}")
                # 如果删除模式为正常删除，则返回错误信息并退出,否则继续执行后续操作
                if delete_mode == 0:
                    return jsonify({'code':2,'msg':f'Ask parent node name:{parent_node_info.name},address:{parent_node_info.address} to delete child node response status code: {response.status_code},error mesg {response.json().get("msg")}'})
        # 将本节点sync_obj_info表中非本节点创建的所有同步对象删除（因为非本节点创建的同步对象都是从父节点获取的，所以需要删除）
        repo_sync_info_db.query(SyncObjInfo).filter(SyncObjInfo.origin!=self_id).delete()
        # 将本节点中的parentId字段清空
        self_node_info.parentId=None
        # 将数据库中父节点信息删除
        repo_sync_info_db.delete(parent_node_info)
        # 将数据库修改提交到数据库文件
        try:
            repo_sync_info_db.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to delete parent node{parent_node_info.name},address:{parent_node_info.address} :repo_sync_info_db commit error: {e}")
            repo_sync_info_db.rollback()
            return jsonify({'code':1,'msg':'Failed to delete parent node'})
        else:
            # 成功删除父节点信息后，需要更新本节点的selfnode_info_sn值
            if update_selfnode_info_sn(self_id):
                current_app.logger.info(f"Delete parent node{parent_node_info.name},address:{parent_node_info.address} successfully")
                return jsonify({'code':0,'msg':'Success in deleting parent node'})
            else:
                current_app.logger.error(f"Delete parent node,but failed to update selfnode_info_sn")
                return jsonify({'code':2,'msg':'Delete parent node,but failed to update selfnode_info_sn'})
            
            

# 接收页面提交的删除子节点请求，删除子节点
@sync_repo_api.route('/delete_child_node',methods=['POST'])
def delete_child_node():
    global self_id
    # 获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取子节点id和auth_code   
    child_id=post_data['id']
    child_parent_auth_code=post_data['auth_code']
    # 获取本节点上存储的该子节点的信息
    child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_id).first()
    # 如果子节点id等于本节点id，则返回错误信息，防止误删除本节点
    if child_id == self_id:
        current_app.logger.error(f'delete child node failed,self node id:{self_id} == child node id:{child_id}')
        return jsonify({'code':1,'msg':'Cannot delete node id equal to self node id'}),401
    # 校验子节点auth_code是否有效，无效则报错退出，防止恶意调用接口删除
    if not child_node.parent_auth_code == child_parent_auth_code:
        current_app.logger.error(f'delete child node failed,auth code not match,child:{child_node.parent_auth_code} != parent:{child_parent_auth_code}')
        return jsonify({'code':1,'msg':'Invalid auth code'}),401
    # 如果子节点auth_code校验有效
    else:
        # 将子节点id从本节点的child_list中删除
        self_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
        self_children_list=json.loads(self_node.children)
        try:
            self_children_list.remove(child_id)
        except Exception as e:
            current_app.logger.error(f"Failed to delete child node:{child_id} from self node:{self_id} children list:{self_children_list}, error msg:{e}")
            return jsonify({'code':1,'msg':f"Failed to delete child node:{child_id} from self node:{self_id} children list:{self_children_list}, error msg:{e}"})
        else:
            current_app.logger.info(f'delete child node:{child_id} from self node:{self_id} children list:{self_children_list}')
        self_node.children=json.dumps(self_children_list)
        # 将子节点标记为删除，当子节点发送心跳请求时，会发现自己已被父节点删除，然后自动删除自己
        child_node.is_delete=True
        # 将子节点从pshared_db的node_status表中删除
        pshared_db.query(NodeStatus).filter_by(id=child_id).delete()
        # 将子节点的所有子节点也标记为删除
        child_children_list=json.loads(child_node.children)
        for child_child_id in child_children_list:
            child_child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_child_id).first()
            child_child_node.is_delete=True
            # 同时删除pshared中的子子节点信息
            pshared_db.query(NodeStatus).filter_by(id=child_child_node.id).delete()
        try:
            pshared_db.commit()
        except Exception as e:
            current_app.logger.error(f"pshared_db commit error: {e}")
            pshared_db.rollback()
        # 将数据库修改提交到repo_sync_info_db数据库文件
        try:
            repo_sync_info_db.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to delete child node id:{child_id} : repo_sync_info_db commit error: {e}")
            repo_sync_info_db.rollback()
            return jsonify({'code':1,'msg':'Failed to delete child node'})
        else:
            current_app.logger.info(f"Delete child node id:{child_id} successfully")
            return jsonify({'code':0,'msg':'Success in deleting child node'})

# 接收页面提交的添加的同步内容
@sync_repo_api.route('/add_sync_obj',methods=['POST'])
def add_sync_obj():
    global self_id
    # 获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取同步对象信息
    objtype=post_data['objtype']
    syncobj=post_data['syncobj']
    # 如果是脚本目录
    if objtype == 'script-dir':
        # 获取脚本目录的description
        description=post_data['description']
        # 获取脚本目录的相对路径，如果syncobj以/开头，则去掉/
        if syncobj.startswith('/'):
            syncobj=syncobj[1:]
        rela_path=syncobj
        # 将输入的syncobj路径转换为绝对路径
        abs_path=to_abs_path(rela_path) 
        # 如果路径不存在或不是目录
        if not abs_path or not os.path.isdir(abs_path):
            current_app.logger.error(f"Failed to add sync object:{syncobj}, not exists or not a directory")
            return jsonify({'code':1,'msg':f"Failed to add sync object,{syncobj} not exists or not a directory"})
        # 如果路径是根目录，则返回错误信息，不允许将根目录作为同步对象
        if abs_path == os.getcwd():
            current_app.logger.error(f"Failed to add sync object:{syncobj}, root directory not allowed")
            return jsonify({'code':1,'msg':f"Failed to add sync object,{syncobj} root directory not allowed"})       
        # 遍历所有script-dir，如果abs_path被包含于于其他同步对象中，则返回错误信息
        for sync_obj_info in repo_sync_info_db.query(SyncObjInfo).filter_by(objtype='script-dir'):
            if abs_path.startswith(sync_obj_info.abs_path):
                current_app.logger.error(f"Failed to add sync object:{syncobj}, path exists in other syncobj")
                return jsonify({'code':1,'msg':f"Failed to add sync object,{syncobj} path exists in other syncobj"})
        # 调用create_git_repo函数创建git仓库
        result=create_git_repo(rela_path)
        if result[0]:
            current_app.logger.info(f"Create git repo for sync object:{syncobj} successfully")
        else:
            current_app.logger.error(f"Failed to create git repo for sync object:{syncobj},error msg:{result[1]}")
            return jsonify({'code':1,'msg':f"Failed to create git repo for sync object,{syncobj},error msg:{result[1]}"})
        # 创建对应的SyncObjInfo对象
        sync_obj_info=SyncObjInfo(objtype=objtype,rela_path=syncobj,abs_path=abs_path,description=description,origin=self_id,sn=1)

    # 如果是deb仓库
    elif objtype == 'deb-repo':
        # 获取仓库地址和仓库codename(仓库的syncobj格式为：仓库相对地址,仓库codename)
        repopath = syncobj.split(', ')[0]
        codename = syncobj.split(', ')[1] 
        abs_path=to_abs_path(repopath)
        # 如果该绝对路径已经存在于其他同步对象中，则返回错误信息
        if repo_sync_info_db.query(SyncObjInfo).filter(and_(SyncObjInfo.objtype == 'deb-repo',SyncObjInfo.abs_path == abs_path,SyncObjInfo.codename == codename)).first():
            current_app.logger.error(f"Failed to add sync object:{syncobj}, path already exists")
            return jsonify({'code':1,'msg':f"Failed to add sync object,{syncobj} path already exists"})
        # 根据codename从deb_repo_info表中读取仓库其他信息
        deb_repo_info=repo_conf_info_db.query(DebRepoInfo).filter(and_(DebRepoInfo.codename == codename,DebRepoInfo.repopath == repopath)).first()
        architectures=deb_repo_info.architectures
        components = deb_repo_info.components 
        description = deb_repo_info.description
        abs_path = deb_repo_info.abs_path
        # 创建对应的SyncObjInfo对象
        sync_obj_info=SyncObjInfo(objtype=objtype,rela_path=repopath,abs_path=abs_path,codename=codename,architectures=architectures,components=components,description=description,origin=self_id,sn=1)
    # 将新创建的SyncObjInfo对象提交到数据库
    try:
        repo_sync_info_db.add(sync_obj_info)
        repo_sync_info_db.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to add sync object:{syncobj}, repo_sync_info_db commit error: {str(e)}")
        repo_sync_info_db.rollback()
        return jsonify({'code':1,'msg':f"Failed to add sync object,type:{objtype},syncobj:{syncobj},repo_sync_info_db commit error: {str(e)}"})
    else:
        if update_selfnode_info_sn(self_id):
            current_app.logger.info(f"Add sync object type:{objtype},syncobj:{syncobj} successfully")
            return jsonify({'code':0,'msg':'Add sync object successfully'})
        else:
            current_app.logger.error(f"Failed to add sync object:{syncobj}, update selfnode_info_sn failed")
            return jsonify({'code':1,'msg':f"Failed to add sync object,type:{objtype},syncobj:{syncobj},update selfnode_info_sn failed"})

# 从数据库中获取同步对象信息，并返回,用于渲染同步对象展示页面
@sync_repo_api.route('/get_sync_obj_list',methods=['GET'])
def get_sync_obj_list():
    global self_id
    # 获取本节点信息
    self_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    # 获取父节点名称
    if self_node.parentId:
        parent_node_name=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_node.parentId).first().name
    else:
        parent_node_name=None
    # 获取所有SyncObjInfo对象
    sync_obj_list=repo_sync_info_db.query(SyncObjInfo).all()
    # 将SyncObjInfo对象列表转换为字典列表，并且判断是否为本节点创建的同步对象
    sync_obj_dict_list=[]
    for obj in sync_obj_list:
        obj_dict={
            'id':obj.id,
            'objtype':obj.objtype,
            'rela_path':obj.rela_path,
            'codename':obj.codename,
            'description':obj.description,
            # 如果origin不等于self_id，则显示为父节点名称，否则显示为本节点名称
            'origin': self_node.name if obj.origin == self_id else parent_node_name,
            'sn': obj.sn,
            'control': True if obj.origin == self_id else False
        }
        sync_obj_dict_list.append(obj_dict)
    return jsonify({'code':0,'data':sync_obj_dict_list})

# 从数据库中删除同步对象信息
@sync_repo_api.route('/delete_sync_obj',methods=['POST'])
def delete_sync_obj():
    global self_id
    # 获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取同步对象id
    obj_id=post_data['id']
    # 根据id从数据库中获取SyncObjInfo对象
    sync_obj_info=repo_sync_info_db.query(SyncObjInfo).filter_by(id=obj_id).first()
    # 如果SyncObjInfo对象不存在，则返回错误信息
    if not sync_obj_info:
        current_app.logger.error(f"Failed to delete sync object,id:{obj_id},not exists")
        return jsonify({'code':1,'msg':f"Failed to delete sync object,id:{obj_id},not exists"})
    # 如果SyncObjInfo对象存在
    else:
        # 删除sync_obj_info表中对应的同步对象信息，node_sync_obj_status表中对应的同步对象信息 
        try:
            pshared_db.query(NodeSyncObjStatus).filter_by(objtype=sync_obj_info.objtype,rela_path=sync_obj_info.rela_path,codename=sync_obj_info.codename).delete()
            repo_sync_info_db.delete(sync_obj_info)
            repo_sync_info_db.commit()
            pshared_db.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to delete sync object,{sync_obj_info.rela_path}, repo_sync_info_db or pshared_db commit error: {str(e)}")
            repo_sync_info_db.rollback()
            return jsonify({'code':1,'msg':f"Failed to delete sync object,{sync_obj_info.rela_path}, repo_sync_info_db or pshared_db commit error: {str(e)}"})
        else:
            if update_selfnode_info_sn(self_id):
                current_app.logger.info(f"Delete sync object {sync_obj_info.rela_path} successfully")
                return jsonify({'code':0,'msg':f"Delete sync object {sync_obj_info.rela_path} successfully"})
            else:
                current_app.logger.error(f"Failed to delete sync object,{sync_obj_info.rela_path}, update selfnode_info_sn failed")
                return jsonify({'code':1,'msg':f"Failed to delete sync object,{sync_obj_info.rela_path}, update selfnode_info_sn failed"})
            
# 对syncobj执行git commit操作
@sync_repo_api.route('/git_commit',methods=['POST'])
def git_commit():
    # 获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取同步对象id
    obj_id=post_data['id']
    # 根据id从数据库中获取SyncObjInfo对象
    sync_obj_info=repo_sync_info_db.query(SyncObjInfo).filter_by(id=obj_id).first()
    # 如果SyncObjInfo对象不存在，则返回错误信息
    if not sync_obj_info:
        current_app.logger.error(f"Failed to git commit,syncobj id:{obj_id},not exists")
        return jsonify({'code':1,'msg':f"Failed to git commit,syncobj id:{obj_id},not exists"})
    # 如果SyncObjInfo对象存在，则执行git commit操作
    else:
        result=commit_git_repo(sync_obj_info.abs_path)
        # 如果git commit执行成功，更新syncobj sn的值，并将node_sync_obj_status表中其他节点的状态全部置为未同步，并则返回成功信息
        if result[0]:
            sync_obj_info.update_sn()
            # 将该syncobj 的同步状态全部置为未同步
            pshared_db.query(NodeSyncObjStatus).filter_by(objtype=sync_obj_info.objtype,rela_path=sync_obj_info.rela_path,).update({'status':False})
            try:
                pshared_db.commit()
                repo_sync_info_db.commit()
            except Exception as e:
                current_app.logger.error(f"Git commit successfully, but failed to update sn sync status for syncobj:{sync_obj_info.rela_path},error: {str(e)}")
                repo_sync_info_db.rollback()
            else:
                current_app.logger.info(f"Git commit for syncobj:{sync_obj_info.rela_path} successfully")
                return jsonify({'code':0,'msg':f"Git commit for syncobj:{sync_obj_info.rela_path} successfully"})
        # 如果git commit执行失败，则返回错误信息
        else:
            current_app.logger.error(f"Failed to git commit for syncobj:{sync_obj_info.rela_path},error msg:{result[1]}")
            return jsonify({'code':1,'msg':f"Failed to git commit for syncobj:{sync_obj_info.rela_path},error msg:{result[1]}"})
        

# 定义后台任务
bg_scheduler = BackgroundScheduler({
    'apscheduler.executors.default': ThreadPoolExecutor(1),
    'apscheduler.executors.processpool': ProcessPoolExecutor(1),
    'apscheduler.job_defaults.coalesce': True,
    'apscheduler.job_defaults.max_instances': 1,
    'apscheduler.timezone': 'Asia/Shanghai'
    }
)

# 添加定时任务，每隔N秒执行，注意：这里实际执行间隔还会被func_class_define的heartbeat_interval_lock时间影响
bg_scheduler.add_job(func=heart_beat, args=[self_id,10],trigger='interval', seconds=10,max_instances=1,coalesce=True)
# 添加定时任务，每隔N秒执行，注意：这里实际执行间隔还会被func_class_define的syncjob_interval_lock时间影响
bg_scheduler.add_job(func=sync_job, args=[self_id,10],trigger='interval', seconds=10,max_instances=1,coalesce=True)
# 启动定时任务
bg_scheduler.start()


            


