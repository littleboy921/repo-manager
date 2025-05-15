import os
import logging
from logging.handlers import RotatingFileHandler

# 当前脚本文件绝对路径目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# log文件绝对路径
log_file_path = os.path.join(current_dir, '../../logs/init_job.log')
# 节点id文件
id_file = os.path.join(current_dir,'../id.txt')

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


# 读取id文件中的id信息,如果id文件不存在，则生成新的id文件并写入self_id
def get_self_id():
    self_id=''
    if not os.path.exists(id_file):
        logger.info(f'id file not exist!')
        return self_id
    else:       
        with open(id_file, 'r') as rfile:
            self_id=rfile.read()
            #去除换行
            self_id=self_id.replace("\n", "").replace("\r", "")
            #去除空格
            self_id=self_id.strip()
        return self_id

if __name__ == '__main__':
    get_self_id()