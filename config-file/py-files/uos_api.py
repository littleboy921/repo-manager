from flask import Flask,request,render_template,jsonify,Blueprint,current_app
from sqlalchemy import Boolean,Column,Integer,String, DateTime,Boolean,and_,or_,func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base
from typing import List, Tuple, Dict

from db_config import uos_api_Base,task_info_Base,uos_api_db,task_info_db,uos_api_engine,task_info_engine
import udcp_api
import json
import sys
import datetime
import os
import ssl
#import subprocess


uos_api=Blueprint('uos_api',__name__)
# 初始化终端在线状态字典，用于存储终端最新一次在线更新时间
pc_online_status={}
# 当前脚本文件绝对路径目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 定义pc_user_passwd表结构，用于存放密码修改平台传过来的密码修改请求
class pc_user_passwd():
    # 类对象对应表users
    __tablename__='pc_user_passwd'
    pc_name = Column(String(64),primary_key=True,index=True,nullable=False)
    local_username = Column(String(64),primary_key=True,nullable=False)
    passwd = Column(String(64),nullable=False)
    last_modify_time = Column(DateTime)

# 定义udcp_pc表结构对应的类，用于存放从域管平台读取过来的所有终端信息
class udcp_pc(uos_api_Base):
    # 类对象对应表udcp_pc
    __tablename__='udcp_pc'
    id = Column(Integer,primary_key=True,index=True,nullable=False)
    pc_name = Column(String(64),index=True,nullable=False)
    department_id= Column(Integer,index=True,nullable=False)
    host_name = Column(String(64),nullable=False)
    machine_id = Column(String(64),unique=True,nullable=False)
    mac = Column(String(32),nullable=False)
    status = Column(Integer,nullable=False)
    mount_path = Column(String(64),nullable=True)

# 定义udcp_pc_change_record表结构，用于存放终端增量变化数据
class udcp_pc_change_record(uos_api_Base):
    # 类对象对应表udcp_pc_change_record
    __tablename__='udcp_pc_change_record'
    id = Column(Integer,primary_key=True,index=True, autoincrement=True)
    pc_name = Column(String(64),index=True,nullable=False)
    machine_id = Column(String(64),unique=True,nullable=False)
    action = Column(String(16),nullable=False)

# 定义task_info_list表结构，用于存放历史任务名称信息
class task_info_list(uos_api_Base):
    # 类对象对应表
    __tablename__='task_info_list'
    id = Column(Integer,primary_key=True,index=True, autoincrement=True)
    task_name = Column(String(64),unique=True,nullable=False)
    create_at = Column(DateTime,nullable=False)
    last_update = Column(DateTime,nullable=False)

uos_api_Base.metadata.create_all(uos_api_engine, checkfirst=True)
task_info_Base.metadata.create_all(task_info_engine, checkfirst=True)
# 用于从json文件中读取值并映射为具体数据类型
_type_lookup = {"integer": Integer, "string": String, "json": JSON, "datetime": DateTime}

# 定义函数，用于将json文件中指定的表结构映射为Base的sqlalchemy的类对象
def mapping_for_json(json_cls_schema):
    clsdict = {"__tablename__": json_cls_schema["tablename"],"__table_args__":{'extend_existing': True} }
    clsdict.update(
        {
            rec["name"]: Column(
                _type_lookup[rec["type"]],
                primary_key=rec.get("is_pk", False),
                autoincrement=rec.get("is_autoincre", False),
                index=rec.get("is_index", False)
            )
            for rec in json_cls_schema["columns"]
        }
    )
    return type(json_cls_schema["clsname"], (task_info_Base,), clsdict)


# 判断当前终端是否在线
# 参数terminal_name：终端名
def if_pc_online(terminal_name:str) -> bool:
    # 设置超时离线时间，间隔超过该时间即视为为离线（单位s）
    offline_time = 50
    # 看终端是否在pc_online_status字典中，不在说明从未上线更新在线时间，即为离线
    if terminal_name in pc_online_status:
        last_update_time = pc_online_status[terminal_name]
        delta_time = datetime.datetime.now() - last_update_time
        delta_time_seconds = delta_time.seconds
        # 间隔时间小于离线时间，视为在线
        if delta_time_seconds < offline_time :
            return True
        else:
            return False
    else:
        return False


# 和域管做终端的全量同步
def fullsync_pcs_with_udcp():
    #删除udcp_pc表中的所有行
    uos_api_db.query(udcp_pc).delete()
    #从域管api接口获取所有终端信息
    get_all_pcs_result=udcp_api.get_all_pcs(udcp_api.conn)
    all_pc_list=get_all_pcs_result.get('result')
    for pc in all_pc_list:
        udcp_pc_record = udcp_pc(
            id=pc.get('id'),
            pc_name = pc.get('name'),
            department_id = pc.get('department_id'),
            host_name = pc.get('host_name'),
            machine_id = pc.get('machine_id'),
            mac = pc.get('mac'),
            status = pc.get('status')            
        )
        uos_api_db.add(udcp_pc_record)
    uos_api_db.commit()

# # 定义ad_user_logon_script表结构，用于存放ad域用户-登录脚本信息
# class ad_user_logon_script(Base):
#     # 类对象对应表ad_user_logon_script
#     __tablename__='ad_user_logon_script'
#     id = Column(Integer,primary_key=True,index=True, autoincrement=True)
#     ad_user = Column(String(64),index=True,unique=True,nullable=False)
#     logon_script = Column(String(128),nullable=False)

# # 定义logon_script_share_driver_path表结构，用于存放登录脚本-共享驱动路径信息
# class logon_script_share_driver_path(Base):
#     # 类对象对应表logon_script_share_driver_path
#     __tablename__='logon_script_share_driver_path'
#     id = Column(Integer,primary_key=True,index=True, autoincrement=True)
#     logon_script = Column(String(128),unique=True,index=True,nullable=False)
#     share_driver_path = Column(String(128),nullable=False)

#uos-api修改指定终端本地用户密码api接口
@uos_api.route('/user-passwd/modify',methods = ['POST'])
def user_passwd_api():
    post_data=request.json
    client_id=post_data.get('client_id')
    client_data=post_data.get('data')
    for post_pc in client_data:
        post_local_username=post_pc.get("local_username")
        post_password=post_pc.get("password")
        for post_pc_name in post_pc.get("pc_names"):
            #查看pc是否在线，否返回错误信息
            if not if_pc_online(post_pc_name):
                error_info={
                    "code": 3,
                    "msg": 'PC not online',
                    "data": post_pc_name
                }
                return jsonify(error_info)
            udcp_pc_search_results=uos_api_db.query(udcp_pc).filter(udcp_pc.pc_name == post_pc_name).all()
            #查看pc是否存在，否返回错误信息
            if  udcp_pc_search_results == []:
                error_info={
                    "code": 2,
                    "msg": 'PC name not exist',
                    "data": post_pc_name
                }                
                return jsonify(error_info)
            pc_passwd_record = pc_user_passwd(
                pc_name = post_pc_name,
                local_username = post_local_username,
                passwd =  post_password,
                last_modify_time = datetime.datetime.now()         
            )
            pc_search_results=uos_api_db.query(pc_user_passwd).filter(pc_user_passwd.pc_name == post_pc_name, pc_user_passwd.local_username == post_local_username).all()
            if pc_search_results == []:
                uos_api_db.add(pc_passwd_record)
            else:
                for pc_search_result in pc_search_results:
                    pc_search_result.passwd=post_password
                    pc_search_result.last_modify_time=datetime.datetime.now()
    try:
        uos_api_db.commit()
        success_info={
            "code": 0,
            "msg": 'password moidfy request recieved',
            "data": ""        
        }
        return jsonify(success_info)
    except :
        uos_api_db.rollback()
        error_info={
            "code": 1,
            "msg": "password moidfy failed",
            "data": ""        
        }           
        return jsonify(error_info),401            

#终端在线状态更新接口，终端上线后定期更新在线时间
@uos_api.route('/pc-api/online',methods = ['POST']) 
def update_pc_online_status():
    post_data=request.json
    machine_id=post_data.get('machine_id')
    terminal_name=post_data.get('terminal_name')
    pc_search_results=uos_api_db.query(udcp_pc).filter(udcp_pc.pc_name == terminal_name, udcp_pc.machine_id == machine_id).all()
    if pc_search_results != []:
        pc_online_status[terminal_name]=datetime.datetime.now()
        success_info={
            "code": 0,
            "msg": "pc status update successfully",
            "data": ""        
        }
        return jsonify(success_info)        
    else:
        error_info={
            "code": 1,
            "msg": "invalid pc",
            "data": ""        
        }           
        return jsonify(error_info),401     

#域管回调接口，用于让域管通知uos-api当前终端增减变化
@uos_api.route('/udcp-webhook',methods = ['POST'])    
def udcp_webhook():
    post_data=request.json
    action=post_data.get("action")
    if action == "DepartmentAddPC":
        machine_id_list=post_data.get('data').get("machine_ids")
        for machine_id in machine_id_list:
            pc=udcp_api.search_terminal_by_machine_id(udcp_api.conn,machine_id)
            udcp_pc_record = udcp_pc(
                id=pc.get('id'),
                pc_name = pc.get('name'),
                department_id = pc.get('department_id'),
                host_name = pc.get('host_name'),
                machine_id = pc.get('machine_id'),
                mac = pc.get('mac'),
                status = pc.get('status')            
            )
            change_record = udcp_pc_change_record(
                pc_name = pc.get('name'),
                machine_id = pc.get('machine_id'),
                action = "insert"
            )
            uos_api_db.add(change_record)
            uos_api_db.add(udcp_pc_record)
    elif action == "UpdatePCDepartment":
        machine_id=post_data.get('data').get("machine_id")
        pc=udcp_api.search_terminal_by_machine_id(udcp_api.conn,machine_id)
        result = uos_api_db.query(udcp_pc).filter(udcp_pc.machine_id == machine_id).first()
        result.department_id = pc.get('department_id')
    elif action == "DeletePC":
        machine_id_list=post_data.get('data').get("machine_ids")
        for machine_id in machine_id_list:
            pc=uos_api_db.query(udcp_pc).filter(udcp_pc.machine_id == machine_id).first()
            uos_api_db.delete(pc)
            change_record = udcp_pc_change_record(
                pc_name = pc.pc_name,
                machine_id = pc.machine_id,
                action = "delete"
            )
            uos_api_db.add(change_record)
    elif action == "OutPCDomain":
        machine_id_list=post_data.get('data').get("machine_ids")
        for machine_id in machine_id_list:
            pc=uos_api_db.query(udcp_pc).filter(udcp_pc.machine_id == machine_id).first()
            uos_api_db.delete(pc)
            change_record = udcp_pc_change_record(
                pc_name = pc.pc_name,
                machine_id = pc.machine_id,
                action = "delete"
            )
            uos_api_db.add(change_record)
    elif action == "DisablePC":
        machine_id_list=post_data.get('data').get("machine_ids")
        for machine_id in machine_id_list:
            result = uos_api_db.query(udcp_pc).filter(udcp_pc.machine_id == machine_id).first()
            result.status=1
    elif action == "EnablePC":
        machine_id_list=post_data.get('data').get("machine_ids")
        for machine_id in machine_id_list:
            result = uos_api_db.query(udcp_pc).filter(udcp_pc.machine_id == machine_id).first()
            result.status=0
    elif action == "UpdatePC":
        machine_id_list=post_data.get('data').get("machine_ids")
        for machine_id in machine_id_list:
            pc=udcp_api.search_terminal_by_machine_id(udcp_api.conn,machine_id)
            result = uos_api_db.query(udcp_pc).filter(udcp_pc.machine_id == machine_id).first()
            result.id = pc.get('id'),
            result.pc_name = pc.get('name'),
            result.host_name = pc.get('host_name'),
            result.mac = pc.get('mac'),
            result.status = pc.get('status')
            change_record = udcp_pc_change_record(
                pc_name = pc.get('name'),
                machine_id = pc.get('machine_id'),
                action = "update"
            )
            uos_api_db.add(change_record)
    try:
        uos_api_db.commit()
        success_info={
            "code": 0,
            "msg": "",
            "data": ""        
        }                  
        return jsonify(success_info),204  
    except:
        uos_api_db.rollback() 
        error_info={
            "code": 1,
            "msg": "udcp-webhook数据增量变化失败",
            "data": sys.exc_info()        
        }           
        return jsonify(error_info),401     


#uos-api平台终端列表全量同步接口
@uos_api.route('/pc-lists/full',methods = ['POST'])
def pc_lists_full_sync():
    post_data=request.json
    client_id=post_data.get('client_id')
    result_lists = uos_api_db.query(udcp_pc.pc_name,udcp_pc.machine_id).all()
    #查询当前变化表中的最大id，以备将来增量同步使用
    '''
    scalar()方法返回查询结果中第一个出现的元素，如果查询结果为空，则返回None；如果查询结果有多条记录，则同样会引发MultipleResultsFound异常。
    这种方法适用于查询返回一个结果或没有返回任何结果的情况，允许空结果的存在
    '''
    max_id = uos_api_db.query(func.max(udcp_pc_change_record.id)).scalar()
    if max_id is None:
        sync_id = 0
    else:
        sync_id = max_id
    #形成一个以udcp_pc.pc_name为key，udcp_pc.machine_id为value的字典
    pc_lists={}
    for pc_tuple in result_lists:
        pc_lists[pc_tuple[0]]=pc_tuple[1]
    #生成返回字典信息
    success_info={
        "code":0,
        "msg":"",
        "data": {
            "pc_lists":pc_lists,
            "sync_id":sync_id
        }        
    }
    return jsonify(success_info)

#uos-api平台终端列表增量同步接口
@uos_api.route('/pc-lists/increment',methods = ['POST'])
def pc_lists_incre_sync():
    post_data=request.json
    client_id=post_data.get('client_id')
    last_sync_id=post_data.get('data').get('last_sync_id')
    result_lists = uos_api_db.query(udcp_pc_change_record.pc_name,udcp_pc_change_record.machine_id,udcp_pc_change_record.action).filter(udcp_pc_change_record.id > last_sync_id).all()
    #查询当前变化表中的最大id，以备将来增量同步使用
    max_id = uos_api_db.query(func.max(udcp_pc_change_record.id)).scalar()
    if max_id is None:
        sync_id = 0
    else:
        sync_id = max_id
    #形成一个以udcp_pc_change_record.pc_name为key，[udcp_pc_change_record.machine_id,udcp_pc_change_record.action]为value的字典
    change_lists={}
    for pc_tuple in result_lists:
        change_lists[pc_tuple[0]]=[pc_tuple[1],pc_tuple[2]]
        success_info={
            "code":0,
            "msg":"",
            "data": {
                "change_lists":change_lists,
                "sync_id":sync_id
            }        
        }
    return jsonify(success_info)

# #  ad_user_logon_script接口，用于更新ad域用户-登录脚本信息
# @uos_api.route('/user-logon-script/user-script',methods = ['POST'])
# def ad_user_logon_script_api():
#     post_data=request.json
#     #client_id用于校验客户端身份
#     client_id=post_data.get('client_id')
#     method=post_data.get('method')
#     if method == "update":
#         userlists=post_data.get('userlists')
#         logon_script=post_data.get('logon_script')
#         for ad_user in userlists:
#             ad_user_logon_script_search_results=uos_api_db.query(ad_user_logon_script).filter(ad_user_logon_script.ad_user == ad_user).all()
#             if ad_user_logon_script_search_results == []:
#                 ad_user_logon_script_record = ad_user_logon_script(
#                     ad_user = ad_user,
#                     logon_script = logon_script
#                 )
#                 uos_api_db.add(ad_user_logon_script_record)
#             else:
#                 for ad_user_logon_script_search_result in ad_user_logon_script_search_results:
#                     ad_user_logon_script_search_result.logon_script=logon_script
#     elif method == "delete":
#         userlists=post_data.get('userlists')
#         for ad_user in userlists:
#             uos_api_db.query(ad_user_logon_script).filter(ad_user_logon_script.ad_user == ad_user).delete()
#     try:
#         uos_api_db.commit()  
#         success_info={    
#             "code": 0,
#             "msg": "",
#             "data": ""        
#         }
#         return jsonify(success_info)
#     except:
#         uos_api_db.rollback()
#         error_info={
#             "code": 1,
#             "msg": "ad user logon script update failed",
#             "data": ""        
#         }           
#         return jsonify(error_info),401    

# #  logon_script_share_driver_path接口，用于更新登录脚本-共享驱动路径信息
# @uos_api.route('/user-logon-script/script-driver-path',methods = ['POST'])
# def logon_script_share_driver_path_api():
#     post_data=request.json
#     #client_id用于校验客户端身份
#     client_id=post_data.get('client_id')
#     method=post_data.get('method')
#     if method == "update":
#         logon_script=post_data.get('logon_script')
#         mount_path_list=post_data.get('mount_path')
#         for mount_path in mount_path_list:
#             logon_script_share_driver_path_record = logon_script_share_driver_path(
#                 logon_script = logon_script,
#                 share_driver_path = mount_path
#             )
#             uos_api_db.add(logon_script_share_driver_path_record)
#     elif method == "delete":
#         logon_script_list=post_data.get('logon_scripts')
#         for logon_script in logon_script_list:
#             uos_api_db.query(logon_script_share_driver_path).filter(logon_script_share_driver_path.logon_script == logon_script).delete()
#     try:
#         uos_api_db.commit()  
#         success_info={    
#             "code": 0,
#             "msg": "",
#             "data": ""        
#         }
#         return jsonify(success_info)
#     except:
#         uos_api_db.rollback()
#         error_info={
#             "code": 1,
#             "msg": "logon script share driver path update failed",
#             "data": ""        
#         }           
#         return jsonify(error_info),401    

# user_share_driver_path接口，用于查询用户-logon脚本信息
@uos_api.route('/user-logon-script/get-user-logon-script',methods = ['POST'])
def get_user_logon_script_api():
    post_data=request.json
    user=post_data.get('user')
    auth_msg=post_data.get('auth_msg')
    # 输出info级别日志
    current_app.logger.info(f'user:{user},auth_msg:{auth_msg}')
    auth_msg_list=auth_msg.split('@',2)
    machine_id=auth_msg_list[0]
    host_name=auth_msg_list[1]
    last_login=auth_msg_list[2]
    pc_info=udcp_api.search_terminal_by_machine_id(udcp_api.conn,machine_id)   
    error_info1={
        "code": 1,
        "msg": "Auth Failed",
        "data": ""        
    }
    if pc_info is None:
        return jsonify(error_info1),411
    terminal_host_name=pc_info.get('host_name')
    # 输出debug级别日志
    current_app.logger.debug(f'terminal_host_name search by machine_id:{terminal_host_name}')
    if terminal_host_name != host_name:
        return jsonify(error_info1),412
    user_info=udcp_api.search_user_by_username(udcp_api.conn,user)
    if user_info is None:
        return jsonify(error_info1),413
    user_last_login=user_info.get('last_login')
    # 输出debug级别日志
    current_app.logger.debug(f'user_last_login:{user_last_login}')
    if not user_last_login.startswith(last_login):
        return jsonify(error_info1),414
    sciptPath=user_info.get('postal_code')
    success_info={    
        "code": 0,
        "msg": "",
        "data": sciptPath      
    }    
    return jsonify(success_info)

# 获取task info list 数据
@uos_api.route('/get_task_info_list/',methods = ['GET'])
def get_task_info_list():
    task_info_list_search_results=uos_api_db.query(task_info_list).all()
    # 形成返回值列表
    result_list=[]
    for task_info_list_search_result in task_info_list_search_results:
        task_name=task_info_list_search_result.task_name
        # 定义表格名称、字段信息
        json_cls_schema = {
            "clsname": task_name,
            "tablename": task_name,
            "columns": [
                {"name": "id", "type": "integer", "is_pk": True,"is_autoincre": True},
                {"name": "pc_name", "type": "string",},
                {"name": "machine_id", "type": "integer",},
                {"name": "data", "type": "json"},
                {"name": "update_time", "type": "datetime"}            
            ],
        }
        # 定义和任务名称对应的表结构类
        task_info_class = mapping_for_json(json_cls_schema)  
        total_rec_num=task_info_db.query(task_info_class).all().count()      
        result_info={
            'task_name': task_info_list_search_result.task_name,
            'create_at': task_info_list_search_result.create_at.strftime("%Y-%m-%d %H:%M:%S"),
            'last_update': task_info_list_search_result.last_update.strftime("%Y-%m-%d %H:%M:%S"),
            'total_rec_num': total_rec_num
        }
        result_list.append(result_info)
    return jsonify({"code": 0, "msg": "","count": len(result_list),"data": result_list})

# 接收终端发送过来的信息，存入到数据库中
@uos_api.route('/add_task_info/',methods = ['POST'])
def add_task_info():
    post_data=request.json
    task_name=post_data.get('task_name')

    # 先查询uos_api_db中任务信息列表中是否已存在该任务名
    task_info_list_search_results=uos_api_db.query(task_info_list).filter(task_info_list.task_name == task_name).all()
    now_time = datetime.datetime.now()
    if task_info_list_search_results == []:
        # 若不存在，则创建该任务名对应的记录
        # 定义任务信息记录实例
        task_info_rec = task_info_list(
            task_name = task_name,
            create_at = now_time,
            last_update = now_time
        )
        uos_api_db.add(task_info_rec)
    else:
        # 若存在，则更新该任务名对应的记录
        for task_info_list_search_result in task_info_list_search_results:
            task_info_list_search_result.last_update = now_time
    try:
        uos_api_db.commit()  
    except Exception as e:
        uos_api_db.rollback()
        error_info={
            "code": 1,
            "msg": str(e),
            "data": ""        
        }
        return jsonify(error_info),403

    # 从post_data中获取任务名称、机器ID、数据信息
    rec = {
        'pc_name': post_data.get('pc_name'),
        'machine_id': post_data.get('machine_id'),
        'data': post_data.get('data') 
    }
    rec['update_time']=now_time
    # 定义表格名称、字段信息
    json_cls_schema = {
        "clsname": task_name,
        "tablename": task_name,
        "columns": [
            {"name": "id", "type": "integer", "is_pk": True,"is_autoincre": True},
            {"name": "pc_name", "type": "string",},
            {"name": "machine_id", "type": "integer",},
            {"name": "data", "type": "json"},
            {"name": "update_time", "type": "datetime"}
        ],
    }

    # 定义和任务名称对应的表结构类
    task_info_class = mapping_for_json(json_cls_schema)
    task_info_Base.metadata.create_all(task_info_engine, checkfirst=True)
    # **rec 表示将字典中的键值对作为参数传递给类实例化
    task_info_rec = task_info_class(**rec)
    # 将数据写入数据库
    task_info_db.add(task_info_rec)
    task_info_db.commit()
    success_info={    
        "code": 0,
        "msg": "upload task info success"   
    }
    return jsonify(success_info)

# 获取task info 数据
@uos_api.route('/get_task_info/',methods = ['GET'])
def get_task_info():
    task_name=request.args.get('task_name')
    # 定义表格名称、字段信息
    json_cls_schema = {
        "clsname": task_name,
        "tablename": task_name,
        "columns": [
            {"name": "id", "type": "integer", "is_pk": True,"is_autoincre": True},
            {"name": "pc_name", "type": "string",},
            {"name": "machine_id", "type": "integer",},
            {"name": "data", "type": "json"},
            {"name": "update_time", "type": "datetime"}            
        ],
    }
    # 定义和任务名称对应的表结构类
    task_info_class = mapping_for_json(json_cls_schema)    
    task_info_search_results=task_info_db.query(task_info_class).all()
    # 形成返回值列表
    result_list=[]
    for task_info_search_result in task_info_search_results:
        result_info={
            'pc_name': task_info_search_result.pc_name,
           'machine_id': task_info_search_result.machine_id,
           'update_time': task_info_search_result.update_time.strftime("%Y-%m-%d %H:%M:%S"),
            'data': task_info_search_result.data
        }
        result_list.append(result_info)
    return jsonify({"code": 0, "msg": "","count": len(result_list),"data": result_list})

# 删除指定task info 数据
@uos_api.route('/del_task_info/',methods = ['GET'])
def del_task_info():
    task_name=request.args.get('task_name')
    # 删除uos_api_db中任务信息列表中的记录
    uos_api_db.query(task_info_list).filter(task_info_list.task_name == task_name).delete()
    try:
        uos_api_db.commit() 
    except Exception as e:
        uos_api_db.rollback()
        error_info={
            "code": 1,
            "msg": str(e),
            "data": ""        
        }
        return jsonify(error_info),403
    # 删除task_info_db中任务名称对应的表结构类
    drop_table_list=[]
    # 定义表格名称、字段信息
    json_cls_schema = {
        "clsname": task_name,
        "tablename": task_name,
        "columns": [
            {"name": "id", "type": "integer", "is_pk": True,"is_autoincre": True},
            {"name": "pc_name", "type": "string"},
            {"name": "machine_id", "type": "integer"},
            {"name": "data", "type": "json"},
            {"name": "update_time", "type": "datetime"}
        ],
    }
    # 定义和任务名称对应的表结构类
    task_info_class = mapping_for_json(json_cls_schema)          
    drop_table_list.append(task_info_class.__table__)
    task_info_Base.metadata.drop_all(task_info_engine, tables=drop_table_list, checkfirst=True)
    try:
        task_info_db.commit() 
    except Exception as e:
        task_info_db.rollback()
        error_info={
            "code": 2,
            "msg": str(e),
            "data": ""        
        }
        return jsonify(error_info),403
    else:
        success_info={    
            "code": 0,
            "msg": "delete task info success",
            "data": ""
        }
        return jsonify(success_info)