from common_func.get_self_id import get_self_id
from db_config import *
from func_define import *
from class_define import *

from flask import Flask,request,jsonify,Blueprint,send_file,render_template,current_app
import json
import datetime
import random
import string
from sqlalchemy import and_,or_,func
import os,time

# 创建蓝图对象
remote_api=Blueprint('remote_api',__name__)
app = Flask(__name__)
#设置正确的时区
os.environ['TZ'] = 'Asia/Shanghai'
time.tzset()
# 全局变量self_id，用于标识本节点的id
self_id = get_self_id()


# 接受添加子节点信息api
@remote_api.route('/add_child_node',methods=['POST'])
def add_child_node():
    global self_id
    # 获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取子节点的parent_auth_code
    parent_auth_code=post_data['auth_code']
    # 获取子节点的repo_sync_info_list
    child_repo_sync_info_list=post_data['repo_sync_info_list']
    # 获取子节点发送过来的信息，第一个元素为直接子节点的信息
    child_node=child_repo_sync_info_list[0]
    # 子节点请求时的远端地址
    child_remote_ip = request.remote_addr
    # 获取本节点信息
    self_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    self_auth_code=self_node.auth_code
    # 校验子节点认证码是否有效，无效则报错退出
    if not self_auth_code == parent_auth_code:
        current_app.logger.error(f"Child ip {child_remote_ip},node id:{child_node['id']} auth code not match,self:{self_auth_code} != child:{parent_auth_code}")
        return jsonify({'code':1,'msg':'Invalid auth code'}),401
    # 判断子节点id是否和本节点id相同，相同则报错
    if child_node['id'] == self_id:
        current_app.logger.error(f"Child node id:{child_node['id']} has same id with self node!")
        return jsonify({'code':2,'msg':f"Child node id:{child_node['id']} has same id with self node!"}),401
    # 判断子节点是否已经在本节点的子节点列表中，存在则报错
    child_node_list=json.loads(self_node.children)
    if child_node['id'] in child_node_list:
        current_app.logger.error(f"Child node id:{child_node['id']}  already exist in children list")
        return jsonify({'code':3,'msg':f"Child node id:{child_node['id']} already exist in children list!"}),401
    # 寻找存在的同名节点
    same_name_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(name=child_node['name']).first()
    # 如果存在同名节点，且未被删除，则返回错误信息并退出
    if same_name_node and same_name_node.is_delete == False:
        current_app.logger.error(f"Child node name already exist,name:{child_node['name']}")
        return jsonify({'code':4,'msg':f"Child node name:{child_node['name']} already exist!"}),401
    # 搜索子节点id是否是被删除过的子节点
    same_id_child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_node['id']).first()
    # 如果子节点已被删除，则先从数据库删除该节点信息,而后再将新的子节点信息写入数据库
    if same_id_child_node and same_id_child_node.is_delete:
        repo_sync_info_db.delete(same_id_child_node)
        current_app.logger.info(f'Delete node that is already deleted,id:{same_id_child_node.id}')
    # 将子节点id写入到本节点children列表中
    children_list=json.loads(self_node.children)
    children_list.append(child_node['id'])
    self_node.children=json.dumps(children_list)
    # 将子节点信息写入到数据库中
    node_info=RepoSyncInfo(
        id=child_node['id'],
        name=child_node['name'],
        address=child_node['address'],
        api_port=child_node['api_port'],
        repo_port=child_node['repo_port'],
        children=json.dumps(child_node['children']),
        description=child_node['description'],
        info_sn=child_node['info_sn'],
        join_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        parentId=self_id,
        parent_auth_code=self_auth_code,
        remote_ip=child_remote_ip,
        is_delete=False
        )
    repo_sync_info_db.add(node_info)
    # 将其子节点上报的其他节点信息写入到数据库中
    for child_node in child_repo_sync_info_list[1:]:
        # 判断节点id是否和本节点id相同，相同则报错
        if child_node['id'] == self_id:
            repo_sync_info_db.rollback()
            return jsonify({'code':2,'msg':'Child node children have id with self node!'}),401
        # 判断节点是否已经在本节点的子节点列表中，存在则报错
        child_node_list=json.loads(self_node.children)
        if child_node['id'] in child_node_list:
            repo_sync_info_db.rollback()
            current_app.logger.error(f"Child node id:{child_node['id']} name:{child_node['name']} children list conflict with self node children list!")
            return jsonify({'code':3,'msg':'Child node children list conflict with self node children list!'}),401
        # 搜索该id是否是被删除过的子节点
        same_id_child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_node['id']).first()
        # 如果节点已被删除，则先从数据库删除该节点信息
        if same_id_child_node and same_id_child_node.is_delete:
            repo_sync_info_db.delete(same_id_child_node)
        # 寻找存在的同名节点
        same_name_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(name=child_node['name']).first()
        # 如果存在同名节点，且未被删除，则报错
        if same_name_node and same_name_node.is_delete == False:
            current_app.logger.error(f"Child node id:{child_node['id']} name:{child_node['name']} already exist!")
            return jsonify({'code':4,'msg':f"Child node name:{child_node['name']} already exist!"}),401 
        # 将节点信息写入到数据库中       
        node_info=RepoSyncInfo(
            id=child_node['id'],
            name=child_node['name'],
            address=child_node['address'],
            api_port=child_node['api_port'],
            repo_port=child_node['repo_port'],  
            children=json.dumps(child_node['children']),
            description=child_node['description'],
            info_sn=child_node['info_sn'],
            join_time=child_node['join_time'],
            parentId=child_node['parentId'],
            remote_ip=child_node['remote_ip'],
            is_delete=child_node['is_delete']
        )
        repo_sync_info_db.add(node_info)
    # 生成随机6位auth_code
    ran_str = ''.join(random.sample(string.ascii_uppercase + string.digits, 6))
    # 更新本节点auth_code值
    self_node.auth_code=ran_str
    # 将数据库修改提交到数据库文件
    try:
        repo_sync_info_db.commit()
    except Exception as e:
        current_app.logger.error(f"Add child node id:{child_node['id']} name:{child_node['name']} failed:repo_sync_info_db commit error: {e}")
        repo_sync_info_db.rollback()
        return jsonify({'code':2,'msg':'Failed to add child node'})
    else:
        current_app.logger.info(f"Add child node id:{child_node['id']}  name:{child_node['name']} successfully")
        # 更新本节点info_sn值
        if update_info_sn(self_id):
            # 返回成功信息，并附带本节点名称信息
            return jsonify({'code':0,'msg':'Success in adding child node','data':{'parent_info_dict':self_node.to_dict()}})
        else:
            current_app.logger.error(f"Error happened when add child node id:{child_node['id']} name:{child_node['name']},failed to update self node info_sn")
            return jsonify({'code':1,'msg':'Failed to update self node info_sn'})

# 接收子节点更新信息，更新本节点信息
@remote_api.route('/update_child_node',methods=['POST'])
def update_child_node():
    global self_id
    #获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取子节点的parent_auth_code
    parent_auth_code=post_data['auth_code']
    # 获取子节点的repo_sync_info_list
    child_repo_sync_info_list=post_data['repo_sync_info_list']
    # repo_sync_info_list的第一个元素为子节点信息，其余为孙子节点信息
    son_node_dict=child_repo_sync_info_list[0]
    child_node_id=son_node_dict['id']
    # 从数据库获取该子节点信息
    child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_node_id).first()
    # 检查该子节点是否已被删除，已删除则报错
    if child_node.is_delete:
        current_app.logger.error(f'Update child node id:{child_node_id} failed:Child node has been deleted!')
        return jsonify({'code':1,'msg':'Child node has been deleted!'}),401
    # 校验该子节点auth_code是否有效，无效则报错退出
    if not child_node.parent_auth_code == parent_auth_code:
        current_app.logger.error(f"child node id:{child_node_id}auth code not match,self:{child_node.parent_auth_code} != child:{parent_auth_code}")
        return jsonify({'code':1,'msg':'Invalid auth code'}),401
    else:
        child_node.name=son_node_dict['name']
        child_node.address=son_node_dict['address']
        child_node.children=json.dumps(son_node_dict['children'])
        child_node.description=son_node_dict['description']
        child_node.info_sn=son_node_dict['info_sn']
        child_node.remote_ip=request.remote_addr
        # 查看是否存在其他未删除的同名节点，存在则报错
        if repo_sync_info_db.query(RepoSyncInfo).filter(and_(RepoSyncInfo.name==son_node_dict['name'],RepoSyncInfo.id!=son_node_dict['id']),RepoSyncInfo.is_delete==False).first():
            current_app.logger.error(f"Update child node id:{child_node_id} failed:Child node name {son_node_dict['name']} already exist!")
            return jsonify({'code':2,'msg':'Child node name already exist!'}),401
        # 遍历其他节点信息列表，找到对应子节点信息，更新其信息
        for other_child_node_info in child_repo_sync_info_list[1:]:
            # 判断节点是否被删除，被删除则也同时将本节点上的该节点标记为删除
            if other_child_node_info['is_delete']:
                repo_sync_info_db.query(RepoSyncInfo).filter_by(id=other_child_node_info['id']).update({'is_delete':True},synchronize_session=False)
            # 未被删除的节点
            else:
                # 从数据库找到对应子节点，并更新其信息
                child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=other_child_node_info['id']).first()
                # 如果子节点不存在，则创建该子节点
                if not child_node:
                    child_node=RepoSyncInfo(
                        id=other_child_node_info['id'],
                        name=other_child_node_info['name'],
                        address=other_child_node_info['address'],
                        children=json.dumps(other_child_node_info['children']),
                        description=other_child_node_info['description'],
                        info_sn=other_child_node_info['info_sn'],
                        join_time=other_child_node_info['join_time'],
                        parentId=other_child_node_info['parentId'],
                        parent_auth_code=other_child_node_info['parent_auth_code'],
                        remote_ip=other_child_node_info['remote_ip'],
                        is_delete=other_child_node_info['is_delete']
                    )
                    repo_sync_info_db.add(child_node)
                # 如果子节点存在，则更新其信息
                else:
                    for key, value in other_child_node_info.items():
                        # 不更新id、online、last_online_time字段
                        if key not in ['id','online','last_online_time'] : 
                            setattr(child_node, key, value)
                # 本节点的该子节点也要标记为未删除
                child_node.is_delete=False
        # 将数据库修改提交到数据库文件
        try:
            repo_sync_info_db.commit()
        except Exception as e:
            current_app.logger.error(f"Update child node id:{child_node_id} failed:repo_sync_info_db commit error: {e}")
            repo_sync_info_db.rollback()
            return jsonify({'code':2,'msg':'Failed to update child node'})
        else:
            current_app.logger.info(f"Update child node id:{child_node_id} name:{son_node_dict['name']} successfully")
            # 更新本节点info_sn值
            if update_info_sn(self_id):
                # 返回更新成功信息，并返回本节点信息
                return jsonify({'code':0,'msg':'Success in updating child node'})
            else:
                current_app.logger.error(f"Failed to update info_sn")
                return jsonify({'code':1,'msg':'Failed to update self node info_sn'})
            
# 接受子节点心跳信息，并返回本节点的selfnode_info_sn信息，以及存储的子节点的info_sn信息，子节点根据本节点的info_sn信息判断是否需要将自身最新信息同步给上级节点，如果发现子节点已被删除，则返回信息要求子节点删除本节点作为其上级节点
@remote_api.route('/child_node_status',methods=['POST'])
def recieve_child_node_status():
    global self_id
    # 获取本节点信息
    self_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    # 获取post请求中的数据
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取子节在线节点的id列表
    online_children_id_list=post_data['online_id_list']
    current_app.logger.debug(f"online child id list is : {online_children_id_list},auth_code is {post_data['auth_code']}")
    # online_children_id_list第一个元素为直接子节点的id
    # 查看本节点的repo_sync_info_db数据库中是否存在子节点信息，如果不存在则返回错误信息（不能要求子节点删除，因为没有对应的auth_code，防止恶意攻击）
    child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=online_children_id_list[0]).first()
    if not child_node:
        current_app.logger.debug(f"Failed to find child node id:{online_children_id_list[0]} in repo_sync_info_db")
        return jsonify({'code':1,'msg':'Failed to find child node in repo_sync_info_db'}),404
    # 如果本节点已存在，则检查auth_code是否有效，无效则报错退出
    elif child_node.parent_auth_code != post_data['auth_code']:
        current_app.logger.debug(f"heartbeat info failed:auth code not match,self:{child_node.parent_auth_code} != child:{post_data['auth_code']}")
        return jsonify({'code':1,'msg':'Invalid auth code'}),401
    # 如果节点存在，且auth_code有效
    else:
        # 如果is_delete为True则返回信息要求子节点删除本节点作为其上级节点
        if child_node.is_delete:
            auth_code=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=online_children_id_list[0]).first().parent_auth_code
            return jsonify({'code':1,'msg':'Child node already been deleted','data':{'is_delete':'true','auth_code':auth_code}}),403
        # 如果本节点未被删除，则更新子节点在线信息，并返回本节点存储的子节点的info_sn信息，以及本节点的selfnode_info_sn信息
        else:
            # 获取本节点的selfnode_info_sn信息
            selfnode_info_sn=self_node.selfnode_info_sn
            # 从数据库获取对应直接子节点的info_sn信息
            direct_child_info_sn=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=online_children_id_list[0]).first().info_sn
            # 查看pshared_db的node_status数据库是否存在子节点信息，如果不存在则创建子节点信息，如果已存在则更新子节点last_update_time
            for child_id in online_children_id_list:
                node_status=pshared_db.query(NodeStatus).filter_by(id=child_id).first()
                if node_status is None:
                    node_status=NodeStatus(id=child_id)
                    pshared_db.add(node_status)
                else:
                    node_status.update_last_update_time()
            try:
                pshared_db.commit()
            except Exception as e:
                current_app.logger.error(f"Failed to update child node status:pshared_db commit error: {str(e)}")
                pshared_db.rollback()
                return jsonify({'code':1,'msg':'Failed to update child node status,pshared_db commit error'}),500
            else:
                current_app.logger.debug(f"Update child node {online_children_id_list} status successfully")
                return jsonify({'code':0,'msg':'Success in updating node status','data':{'info_sn':direct_child_info_sn,'selfnode_info_sn':selfnode_info_sn}})

# 接收子节点发过来的删除信息，并对本节点上的对应子节点数据进行标记删除
@remote_api.route('/delete_child_node',methods=['POST'])
def delete_child_node():
    global self_id
    # 获取post请求中的数据
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取子节点id
    child_id=post_data['id']
    # 获取auth_code
    auth_code=post_data['auth_code']
    # 找到对应子节点信息
    child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_id).first()
    # 如果子节点不存在，说明无需删除，直接返回成功信息
    if not child_node:
        current_app.logger.info(f"Child node id:{child_id} not exist,no need to delete")
        return jsonify({'code':0,'msg':'Success in deleting child node'})
    # 获取本节点存储的对应子节点id的auth_code
    child_auth_code=child_node.parent_auth_code
    # 校验auth_code是否有效，无效则报错退出
    if not auth_code == child_auth_code:
        current_app.logger.error(f'Child node id:{child_id} auth code not match,self:{auth_code} != child:{child_auth_code}')
        return jsonify({'code':1,'msg':'Invalid auth code'}),401
    else:
        # 如果auth_code有效，则从数据库对子节点进行标记
        # 在数据库中标记对应子节点信息为已删除
        child_node.is_delete=True
        # 将子节点从本节点的children_list中删除
        self_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
        children_list=json.loads(self_node.children)
        children_list.remove(child_id)
        self_node.children=json.dumps(children_list)
        # 删除pshared_db memory数据库中对应子节点信息
        pshared_db.query(NodeStatus).filter_by(id=child_id).delete()
        # 获取子节点的children_list
        children_list=json.loads(child_node.children)
        # 将子节点的所有子节点也标记为删除
        child_children_list=json.loads(child_node.children)
        for child_child_id in child_children_list:
            child_child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_child_id).first()
            child_child_node.is_delete=True
            # 同时删除pshared中的子子节点信息
            pshared_db.query(NodeStatus).filter_by(id=child_child_node.id).delete()
        # 将数据库修改提交到数据库文件
        try:
            pshared_db.commit()
        except Exception as e:
            current_app.logger.error(f"pshared_db commit error: {e}")
            pshared_db.rollback()
        
        try:
            repo_sync_info_db.commit()
        except Exception as e:
            current_app.logger.error(f"Child node id:{child_id} ask to delete itself failed:repo_sync_info_db commit error: {str(e)}")
            repo_sync_info_db.rollback()
            return jsonify({'code':2,'msg':'Child node ask to delete itself failed'})
        else:
            current_app.logger.info(f"Child node id:{child_id} ask to delete itself successfully")
            # 更新本节点info_sn值
            if update_info_sn(self_id):
                # 返回更新成功信息，返回删除成功信息
                return jsonify({'code':0,'msg':'Success in deleting child node'})
            else:
                current_app.logger.error(f"Failed to update info_sn")
                return jsonify({'code':1,'msg':'Failed to update info_sn'})
            
# 向子节点提供同步对象信息
@remote_api.route('/get_sync_object',methods=['POST'])
def get_sync_object():
    global self_id
    # 获取本节点信息
    self_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=self_id).first()
    # 获取post请求中的数据
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取子节点id
    child_id=post_data['id']
    # 获取auth_code
    auth_code=post_data['auth_code']
    # 找到对应子节点信息
    child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_id).first()
    # 获取本节点存储的对应子节点id的auth_code
    child_auth_code=child_node.parent_auth_code
    # 校验auth_code是否有效，无效则报错退出
    if not auth_code == child_auth_code:
        current_app.logger.error(f'Child node id:{child_id} auth code not match,self:{auth_code} != child:{child_auth_code}')
        return jsonify({'code':1,'msg':'Invalid auth code'}),401
    else:
        syncobj_info_list=[]
        # 如果auth_code有效，则从数据库获取本节点的自身信息，以及sync_object信息，转化为字典合成列表，返回相关信息
        self_node_dict={
            'id':self_id,
            'name':self_node.name,
            'description':self_node.description,
            'selfnode_info_sn':self_node.selfnode_info_sn,
        }
        # 获取本节点同步对象信息
        syncobj_info_list=[]
        for syncobj in repo_sync_info_db.query(SyncObjInfo).all():
            syncobj_info_list.append(syncobj.to_dict())
        return jsonify({'code':0,'msg':'Success in getting sync object','data':{'syncobj_info_list':syncobj_info_list,'self_node_dict':self_node_dict}})

# 接受子节点发送过来的syncobj sn信息，并返回本节点的syncobjsn信息
@remote_api.route('/get_syncobj_sn',methods=['POST'])
def get_syncobj_sn():
    # 获取post请求中的数据
    post_data=request.json  #将json格式的请求数据转换为字典、列表
    # 获取子节点id
    child_id=post_data['id']
    # 获取auth_code
    auth_code=post_data['auth_code']
    # 找到对应子节点信息
    child_node=repo_sync_info_db.query(RepoSyncInfo).filter_by(id=child_id).first()
    # 获取本节点存储的对应子节点id的auth_code
    child_auth_code=child_node.parent_auth_code
    # 校验auth_code是否有效，无效则报错退出
    if not auth_code == child_auth_code:
        current_app.logger.error(f'Child node id:{child_id} auth code not match,self:{child_auth_code} != child:{auth_code}')
        return jsonify({'code':1,'msg':'Invalid auth code'}),401
    # 如果auth_code有效，则从数据库获取本节点的syncobjsn信息，并返回相关信息
    # 构建返回给子节点的需要同步的need_sync_syncobj_list信息
    need_sync_syncobj_list=[]
    # 构建返回给子节点的已经同步的synced_syncobj_list信息
    synced_syncobj_list=[]
    # 有效，则获取子节点发送的syncobj_list信息，对其中的syncobj逐个对比
    child_syncobj_list= post_data['syncobj_list']
    for child_syncobj in child_syncobj_list:
        # 获取本节点的对应syncobj sn信息
        self_syncobj=repo_sync_info_db.query(SyncObjInfo).filter_by(objtype=child_syncobj['objtype'],rela_path=child_syncobj['rela_path'],codename=child_syncobj['codename']).first()
        # 如果本节点不存在对应syncobj，则忽略该syncobj，否则对sn进行对比
        if self_syncobj:
            # 如果sn不同，则将该syncobj信息添加到返回列表中,并在数据库表node_sync_obj_status中将该syncobj_status设置为false
            if self_syncobj.sn != child_syncobj['sn']:
                need_sync_syncobj_list.append(
                    {
                        'objtype':self_syncobj.objtype,
                        'rela_path':self_syncobj.rela_path,
                        'codename':self_syncobj.codename,
                        'sn':self_syncobj.sn,
                    }
                )
                node_sync_obj_status=pshared_db.query(NodeSyncObjStatus).filter_by(node_id=child_id,objtype=child_syncobj['objtype'],rela_path=child_syncobj['rela_path'],codename=child_syncobj['codename']).first()
                # 如果不存在该syncobj_status记录，则创建该记录
                if node_sync_obj_status is None:
                    node_sync_obj_status=NodeSyncObjStatus(node_id=child_id,objtype=child_syncobj['objtype'],rela_path=child_syncobj['rela_path'],codename=child_syncobj['codename'],status=False)
                    pshared_db.add(node_sync_obj_status)
                # 如果存在该syncobj_status记录，则更新syncobj_status为false
                else:
                    node_sync_obj_status.status=False
            # 如果sn相同，则在数据库表node_sync_obj_status中将该syncobj_status设置为true，并将该syncobj信息添加到synced_syncobj_list列表中
            else:
                synced_syncobj_list.append(
                    {
                        'objtype':self_syncobj.objtype,
                        'rela_path':self_syncobj.rela_path,
                        'codename':self_syncobj.codename,
                    }
                )
                node_sync_obj_status=pshared_db.query(NodeSyncObjStatus).filter_by(node_id=child_id,objtype=child_syncobj['objtype'],rela_path=child_syncobj['rela_path'],codename=child_syncobj['codename']).first()
                # 如果不存在该syncobj_status记录，则创建该记录
                if node_sync_obj_status is None:
                    node_sync_obj_status=NodeSyncObjStatus(node_id=child_id,objtype=child_syncobj['objtype'],rela_path=child_syncobj['rela_path'],codename=child_syncobj['codename'],status=True)
                    pshared_db.add(node_sync_obj_status)
                # 如果存在该syncobj_status记录，则更新syncobj_status为true
                else:
                    node_sync_obj_status.status=True
    # 将need_sync_syncobj_list返回给子节点
    return jsonify({'code':0,'msg':'Success in getting syncobj sn','data':{'need_sync_syncobj_list':need_sync_syncobj_list,'synced_syncobj_list':synced_syncobj_list}})
                