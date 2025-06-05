#!/usr/bin/python
import http.client
import ssl
import json
import os
import time
from typing import List, Tuple, Dict

# 当前脚本文件绝对路径目录
current_dir = os.path.dirname(os.path.abspath(__file__))
#客⼾端证书⽂件路径
certfile = os.path.join(current_dir,"crts_keys/app.crt")
#客⼾端私钥⽂件路径
keyfile = os.path.join(current_dir,"crts_keys/app.key")
#服务端CA证书
cafile = os.path.join(current_dir,"crts_keys/openapi_ca.crt")
# 域管api接口地址
udcp_api_url="udcp-openapi.test.com"

#初始化https连接
ssl_ctx = ssl.SSLContext()
try:
    ssl_ctx.load_cert_chain(certfile, keyfile)
    ssl_ctx.load_verify_locations(cafile)
except:
    print("加载证书失败")
else:
    print("加载证书成功")
conn = http.client.HTTPSConnection(udcp_api_url, context = ssl_ctx)

#获取部门信息
def get_department(conn):
    #部⻔管理-获取部⻔列表
    conn.request("GET", "/openapi/uim/v1/app/departments")
    resp = conn.getresponse()
    print(json.loads(resp.read()))

#新增人员
def add_user(conn):
    body = {
      "username":"zhangsi",    #非空
      "full_name":"张四four",           #非空
      "department_id":3,             #非空
      "password":"88888888",         #非空
      "utype":0,                     #非空
      "remark":"测试",              #备注字段
      "job_number":"111", 
      "phone":"13476835478", 
      "email":"wwww@163.com", 
      "province":"湖北省", 
      "city":"武汉市", 
      "street":"⽆名街", 
      "postal_code":"430000", 
      "type":"研发⼯程师"
    }
    conn.request(
        "POST", "/openapi/uim/v1/app/user",
        body = json.dumps(body),
        headers = {"content-type":"application/json"}
    )
    resp = conn.getresponse()
    print(json.loads(resp.read()))
    
#查询人员
def search_user_by_username(conn,username):
    conn.request(
        "GET", 
        f"/openapi/uim/v1/app/user?username={username}",
    )
    for i in range(4):  # 最多重试4次
        try:
            resp = json.loads(conn.getresponse().read())
            return resp.get('data')
        except Exception as e:
            print(f"查询用户{username}，执行报错,错误类型：{type(e)},错误信息：{e}")
            deplay=(i+1)*0.5
            time.sleep(deplay)

#更新人员
def update_user(conn,user):
    body = {
      "id":user.get('id'),
      "full_name":user.get('full_name'),
      "department_id":user.get('department_id'),
      "utype":0,
      "remark":"api update user",
      "status":0,
      "job_number":"",
      "phone":"",
      "email":"",
      "province":"",
      "city":"",
      "street":"",
      "postal_code":"",
      "type":""
    }
    try:
        conn.request(
            "PATCH", 
            "/openapi/uim/v1/app/user",
            body = json.dumps(body),
            headers = {"content-type":"application/json"}
        )
    except:
        print(f"更新用户{user.get('username')}，执行报错")
    else:
        print(f"更新用户{user.get('username')}")
    finally:
        resp = conn.getresponse()
        print(json.loads(resp.read()))

#删除人员
def del_user(conn):
    body = {
      "ids": [1,6]
    }
    conn.request(
        "DELETE", "/openapi/uim/v1/app/user",
        body = json.dumps(body),
        headers = {"content-type":"application/json"}
    )
    resp = conn.getresponse()
    print(json.loads(resp.read()))


#新增部门
def add_department(conn):
    #部⻔管理-新增部⻔
    body = {
      "name": "department13",
      "parent_id": 11,
      "des": "department13desc",
      "code": "44645"
    }
    conn.request(
        "POST", "/openapi/uim/v1/app/department",
        body = json.dumps(body),
        headers = {"content-type":"application/json"}
    )
    resp = conn.getresponse()
    print(json.loads(resp.read()))

#删除部门
def del_department(conn):
    body = {
      "id": 32
    }
    conn.request(
        "DELETE", "/openapi/uim/v1/app/department",
        body = json.dumps(body),
        headers = {"content-type":"application/json"}
    )
    resp = conn.getresponse()
    print(json.loads(resp.read()))

#获取所有终端信息列表
def get_all_pcs(conn:http.client.HTTPSConnection,) -> Dict:
    conn.request(
        "GET", 
        #f"/openapi/uim/v1/app/pcs?page=1&rows=100"
        f"/openapi/uim/v1/app/pcs?rows=100000"
    )
    resp = json.loads(conn.getresponse().read())
    #print(resp)
    all_pc_lists_result=resp.get('data')
    return all_pc_lists_result

#查询终端id信息，返回符合keyword的pc_id的列表，根据keyword查询终端信息，keyword支持终端名称和终端ip
def search_terminal_id(conn:http.client.HTTPSConnection,pc_keyword:str) -> List: 
    conn.request(
        "GET",
        f'/openapi/uim/v1/app/pcs?keyword={pc_keyword}'
    )
    resp = json.loads(conn.getresponse().read())
    #terminal_id=resp.get('data').get('result')[0].get('id')
    result_list=resp.get('data').get('result')
    key='id'
    terminal_id_list=[d[key] for d in result_list if key in d]
    return(terminal_id_list)

# 根据machine_id搜索终端信息
def search_terminal_by_machine_id(conn:http.client.HTTPSConnection,machine_id:str) -> Dict:
    conn.request(
        "GET",
        f'/openapi/uim/v1/app/pcs?machine_ids={machine_id}'
    )
    for i in range(4):  # 最多重试3次
        try:
            resp = json.loads(conn.getresponse().read())
            result_pc_dict=resp.get('data').get('result')[0]
            return result_pc_dict
        except Exception as e:
            print(f"查询终端machine_id{machine_id}，执行报错,错误类型：{type(e)},错误信息：{e}")
            delay=(i+1)*0.5
            time.sleep(delay)
    
#获取列表信息
def get_tags(conn):
    conn.request(
        "GET", 
        f"/openapi/uim/v1/app/tags?rows=100000",
    )
    resp = json.loads(conn.getresponse().read())
    print(resp)
    return resp     



#传入pc_id新增任务
def add_script_job(conn,pc_id: List[str],script_name: str):
    pc_id_list=[]
    pc_id_list.append(str(pc_id))
    body = {
        "type": 1003,
        "period_type": 33280,
        "target_type": 33793,
        "content": {
            "script": {
                "script_name": "test_api",
                "file_url": f"{script_name}",
                "script_content": ""
            }
        },
        "pc_ids": pc_id_list,
        "department_ids": [],
        "app_id": ""
    }
    conn.request(
        "POST", "/openapi/job/v3/app/task",
        body = json.dumps(body),
        headers = {"content-type":"application/json"}
    )
    resp = conn.getresponse()
    print(json.loads(resp.read()))


#主函数
def main():
    #get_department(conn)
    #del_department(conn)
    #获取所有终端信息
    #get_all_pcs(conn)
    # -- 根据终端名称下发任务 ---
    #pc_id=search_terminal_id(conn,'ipason')
    #print(pc_id)
    # add_script_job(conn,pc_id)
    #---根据终端machine_id搜索终端信息---
    pc_info=search_terminal_by_machine_id(conn,'e3a402f8cd2b2d3a24e5230c86bc0489')
    print(json.dumps(pc_info, indent=4))
    # ------------------
    #add_user(conn)
    #print(json.dumps(get_terminal(conn), indent=4))
    #print(json.dumps(get_tags(conn), indent=4))
    #add_script_job(conn)
    # 搜索用户信息
    user_info=search_user_by_username(conn,'pfj')
    print(json.dumps(user_info, indent=4))
    print(user_info.get('postal_code'))
    # -- 根据账户名来更新账户信息的实现 ---
    #user=search_user(conn,'person02')
    #print(user)
    #update_user(conn,user)
    #get_tags(conn)
    # -- 


if __name__ == "__main__":
  main()
