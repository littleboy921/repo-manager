from db_config import *
from class_define import *
from common_func.fetch_nginx_ports import fetch_nginx_ports
from common_func.get_self_id import get_self_id
import logging
from logging.handlers import RotatingFileHandler
import os
import random
import string

# 当前脚本文件绝对路径目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# log文件绝对路径
log_file_path = os.path.join(current_dir, '../logs/init_job.log')
# 创建logger对象
logger = logging.getLogger('init_logger')
logger.setLevel(logging.DEBUG)
# 创建RotatingFileHandler对象，设置日志文件最大大小为10M，保存日志文件个数为10
file_handler = RotatingFileHandler(log_file_path, maxBytes=10*1024*1024, backupCount=10)
file_handler.setLevel(logging.INFO)
# 创建formatter对象，设置日志格式
formatter = logging.Formatter("[%(asctime)s][%(filename)s:%(lineno)d][%(levelname)s][%(thread)d] - %(message)s")
file_handler.setFormatter(formatter)
# 将RotatingFileHandler添加到logger对象中
logger.addHandler(file_handler)

# 定义函数：初始化指定id节点数据库，目前仅用于本节点初始化
# args: id: 节点id
def init_repo_sync_info_db(id:str):
    # 每次启动时，清空pshared_db_Base数据库所有数据
    pshared_db_Base.metadata.drop_all(pshared_db_engine)
    # 在输出库中创建表
    # checkfirst=True，默认值为True，表示创建表前先检查该表是否存在，如同名表已存在则不再创建。其实默认就是True
    uos_api_Base.metadata.create_all(uos_api_engine, checkfirst=True)
    task_info_Base.metadata.create_all(task_info_engine, checkfirst=True)
    repo_sync_info_Base.metadata.create_all(repo_sync_info_engine, checkfirst=True)
    pshared_db_Base.metadata.create_all(pshared_db_engine,checkfirst=True)
    repo_conf_info_Base.metadata.create_all(repo_conf_info_engine, checkfirst=True)
    repo_update_info_Base.metadata.create_all(repo_update_info_engine,checkfirst=True)
    
    # 如果数据库中没有本节点信息，则先创建本节点信息，并写入数据库
    repo_node = repo_sync_info_db.query(RepoSyncInfo).filter_by(id=id).first()
    if repo_node is None:
        # 获取nginx相关端口信息
        nginx_ports=fetch_nginx_ports()
        # 生成随机6位auth_code
        ran_str = ''.join(random.sample(string.ascii_uppercase + string.digits, 6))
        new_node = RepoSyncInfo(id=id,auth_code=ran_str,api_port=nginx_ports[0],repo_port=nginx_ports[1])
        repo_sync_info_db.add(new_node)
        try:
            repo_sync_info_db.commit()
        except Exception as e:
            logger.error(f"repo_sync_info_db commit error: {e}")
            repo_sync_info_db.rollback()
            return False
        else:
            logger.info(f"Init repo_sync_info_db success")
            return True
    else:
        return True

if __name__ == '__main__':
    self_id = get_self_id()
    if self_id != '':
        logger.info(f"self id is {self_id}")
    else:
        logger.error(f"Cannot get self id,self id is empty")
    init_repo_sync_info_db(self_id)