from db_config import *
from common_func.render_tpl import render_tpl
from common_func.get_self_id import get_self_id
from sqlalchemy import Boolean,Column,Integer,String, DateTime,Boolean,and_,or_,func
import json
import datetime

# 定义类:repo_sync_info对应表结构
class RepoSyncInfo(repo_sync_info_Base):
    # 类对象对应表repo_sync_info
    __tablename__='repo_sync_info'
    id = Column(String(64),primary_key=True,index=True,nullable=False)
    name=Column(String(64))
    address = Column(String(64))
    api_port = Column(String(6),nullable=False)
    repo_port = Column(String(6),nullable=False)
    auth_code = Column(String(8))
    children = Column(String(),default='[]')
    description=Column(String(256))
    info_sn=Column(String(64))   # info_sn主要是用来向上汇报本节点以及子节点的信息状态，上级节点通过info_sn可以感知本节点及其子节点的状态变化
    selfnode_info_sn=Column(String(64))   # selfnode_info_sn主要是用来向同步本节点的状态，下级节点通过selfnode_info_sn可以感知本节点的状态变化
    join_time=Column(String(24))  # 这里的时间仅用于前端展示，并不参与任何计算，所以可以直接用字符串存储,格式为%Y-%m-%d %H:%M:%S
    parentId=Column(String(64))
    parent_auth_code=Column(String(8))
    remote_ip=Column(String(64))
    is_delete=Column(Boolean,default=False)

    # def time_to_str(self,time_obj):
    #     if time_obj is None:
    #         return ''
    #     else:
    #         return time_obj.strftime('%Y-%m-%d %H:%M:%S')
    # 这个函数用于将对象的某些属性转换为字典，汇报信息给上级节点，或渲染不含status状态的页面
    def to_dict(self)->dict:
        # 如果节点已删除，则返回is_delete为True的字典
        if self.is_delete:
            return {
                'id': self.id,
                'is_delete': True
            }
        # 如果节点未删除，则返回除status信息以外的信息
        else:
            return {
                'id': self.id,
                'name': self.name,
                'address': self.address,
                'api_port': self.api_port,
                'repo_port': self.repo_port,
                'children': json.loads(self.children),
                'description': self.description,
                'info_sn': self.info_sn,
                'join_time': self.join_time,
                'parentId': self.parentId,
                'parent_auth_code': self.parent_auth_code,
                'remote_ip': self.remote_ip,
                'is_delete': self.is_delete
            }        
    # 这个函数用于将对象的某些属性转换为字典，带有status状态，用于前端页面的树形结构展示
    def to_dict_with_status(self)->dict:  
        if self.is_delete:
            return {
                'id': self.id,
                'is_delete': True
            }
        else:
            # 获取pshared_db中的node_status，节点在线状态信息
            node_status = pshared_db.query(NodeStatus).filter_by(id=self.id).first()
            # 初始化sync_status为None，表示未获取到同步状态信息
            sync_status = None
            # 获取pshared_db中的node_sync_obj_status，节点同步对象状态信息
            all_sync_obj_status_list = pshared_db.query(NodeSyncObjStatus).filter_by(node_id=self.id).all()
            for sync_obj_status in all_sync_obj_status_list:
                # 只要有一个同步对象状态为False，则该节点的同步状态即为False
                if sync_obj_status.status is False:
                    sync_status = False
                    break
                else:
                    sync_status = True
            # 如果node_status不存在，说明是本节点或该子节点还未发送心跳
            if node_status is None:
                # 如果是本节点，则online信息为True
                if self.id == get_self_id():
                    return {
                        'id': self.id,
                        'name': self.name,
                        'address': self.address,
                        'api_port': self.api_port,
                        'repo_port': self.repo_port,
                        'children': json.loads(self.children),
                        'description': self.description,
                        'info_sn': self.info_sn,
                        'join_time': self.join_time,
                        'online': True,
                        'sync_status': sync_status,
                        'last_online_time': None,
                        'parentId': None,  # 不返回父节点的id信息，因为会导致前端树形结构显示不正常
                        'remote_ip': self.remote_ip,
                        'is_delete': self.is_delete
                    }
                # 是子节点或父节点，但未收到心跳信号，则online信息为False
                else:
                    return {
                        'id': self.id,
                        'name': self.name,
                        'address': self.address,
                        'api_port': self.api_port,
                        'repo_port': self.repo_port,
                        'children': json.loads(self.children),
                        'description': self.description,
                        'info_sn': self.info_sn,
                        'join_time': self.join_time,
                        'online': False,
                        'sync_status': sync_status,
                        'last_online_time': None,
                        'parentId': self.parentId,
                        'parent_auth_code': self.parent_auth_code,
                        'remote_ip': self.remote_ip,
                        'is_delete': self.is_delete
                    }
            # 如果node_status存在，则根据node_status信息判断节点online值
            else:
                return {
                    'id': self.id,
                    'name': self.name,
                    'address': self.address,
                    'api_port': self.api_port,
                    'repo_port': self.repo_port,
                    'children': json.loads(self.children),
                    'description': self.description,
                    'info_sn': self.info_sn,
                    'join_time': self.join_time,
                    'online': node_status.check_node_online(),
                    'sync_status': sync_status,
                    'last_online_time': node_status.last_update_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'parentId': self.parentId,
                    'parent_auth_code': self.parent_auth_code,
                    'remote_ip': self.remote_ip,
                    'is_delete': self.is_delete
                } 
             
# 定义类：同步对象信息，存储要同步的仓库、脚本目录等信息
class SyncObjInfo(repo_sync_info_Base):
    # 类对象对应表sync_object_info
    __tablename__='sync_obj_info'
    id = Column(Integer,primary_key=True,index=True, autoincrement=True)
    objtype = Column(String(64),nullable=False)
    rela_path = Column(String(256),nullable=False) # 相对路径，接收前端传入的路径
    abs_path = Column(String(256)) # 绝对路径，根据rela_path计算得到
    codename = Column(String(64))
    architectures = Column(String(64))
    components = Column(String(256))
    description = Column(String(256))
    origin=Column(String(64),nullable=False)   # 来源节点id，如果是本节点，则填入本节点id
    sn=Column(Integer,default=0)
    def to_dict(self):
        return {
            'id': self.id,
            'objtype': self.objtype,
            'rela_path': self.rela_path,
            'codename': self.codename,
            'architectures': self.architectures,
            'components': self.components,
            'description': self.description if self.description else '',
            'origin': self.origin,
            'sn': self.sn
        }
    def update_sn(self):
        self.sn += 1
         
# 定义类：节点状态
class NodeStatus(pshared_db_Base):
    # 类对象对应表node_status
    __tablename__='node_status'
    id=Column(String(64),primary_key=True,index=True,nullable=False) 
    last_update_time=Column(DateTime,default=datetime.datetime.now())

    def update_last_update_time(self):
        self.last_update_time = datetime.datetime.now()
    def check_node_online(self):
        # 设置超时离线时间，间隔超过该时间即视为为离线（单位s）
        offline_time = 30
        delta_time = datetime.datetime.now() - self.last_update_time
        delta_time_seconds = delta_time.seconds
        # 间隔时间小于离线时间，视为在线
        if delta_time_seconds < offline_time :
            return True
        else:
            return False

# 定义类：节点syncobj状态信息
class NodeSyncObjStatus(pshared_db_Base):
    # 类对象对应表node_sync_obj_status
    __tablename__='node_sync_obj_status'
    id=Column(Integer,primary_key=True,index=True,nullable=False,autoincrement=True)
    node_id=Column(String(64),nullable=False)
    objtype=Column(String(64),nullable=False)
    rela_path=Column(String(256),nullable=False)
    codename=Column(String(64))
    status=Column(Boolean,default=False)

# 定义类：全局共享变量
class GlobalVar(pshared_db_Base):
    # 类对象对应表global_var
    __tablename__='global_var'
    id=Column(String(64),primary_key=True,index=True,nullable=False) 
    value=Column(String(256),default='')

# 定义类：deb仓库配置信息
class DebRepoInfo(repo_conf_info_Base):
    # 类对象对应表deb_repo_info
    __tablename__='deb_repo_info'
    id = Column(Integer,primary_key=True,index=True, autoincrement=True)
    repopath = Column(String(256),nullable=False)
    abs_path = Column(String(256),nullable=False)
    codename = Column(String(64),nullable=False)
    architectures = Column(String(64),nullable=False)
    components = Column(String(256),nullable=False)
    description = Column(String(256),nullable=False)
    size = Column(Integer,nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
           'repopath': self.repopath,
            'abs_path': self.abs_path,
            'codename': self.codename,
            'architectures': self.architectures,
            'components': self.components,
            'description': self.description,
            'size': self.size
        }

# 定义类：deb仓库update相关信息
class DebUpdateInfo(repo_update_info_Base):
    # 类对象对应表deb_repo_update_info
    __tablename__='deb_repo_update_info' 
    id = Column(Integer,primary_key=True,index=True, autoincrement=True)
    codename = Column(String(64),nullable=False)
    component = Column(String(256),nullable=False)
    arch = Column(String(64),nullable=False)
    deb_name = Column(String(128),nullable=False)   
    update_conf_name=Column(String(64),nullable=False)
    file_rel_path= Column(String(256),nullable=False)
    updated_time=last_update_time=Column(DateTime,nullable=True)

if __name__ == '__main__':
    # checkfirst=True，默认值为True，表示创建表前先检查该表是否存在，如同名表已存在则不再创建。其实默认就是True
    uos_api_Base.metadata.create_all(uos_api_engine, checkfirst=True)
    task_info_Base.metadata.create_all(task_info_engine, checkfirst=True)
    repo_sync_info_Base.metadata.create_all(repo_sync_info_engine, checkfirst=True)
    pshared_db_Base.metadata.create_all(pshared_db_engine,checkfirst=True)
    repo_conf_info_Base.metadata.create_all(repo_conf_info_engine, checkfirst=True)
    repo_update_info_Base.metadata.create_all(repo_update_info_engine, checkfirst=True)     