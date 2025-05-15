import os
from flask import current_app
from common_func.render_tpl import render_tpl
# 通过传入的配置文件字典信息，创建deb仓库配置文件
def create_deb_repo_conf(abs_path:str,distributions_conf_data:dict,update_conf_data:dict)->bool:    
    # 仓库conf目录路径
    conf_dir=os.path.join(abs_path,'conf')
    # 如果conf目录不存在，则创建对应目录以及distributions和update配置文件
    if not os.path.exists(conf_dir):
        # 递归创建deb仓库目录及其conf目录，并设置权限，0o表示八进制
        try:
            os.makedirs(conf_dir, mode=0o755)
        except Exception as e:
            current_app.logger.error(f"Failed to create deb repo conf directory: {e}")
            # 若创建目录失败，则返回False
            return False
        else:
            current_app.logger.info(f"Create deb repo conf directory successfully")
        # 通过jinjia2模板生成distributions配置文件
        if render_tpl('deb-repo','distributions.j2',os.path.join(conf_dir,'distributions'),distributions_conf_data):
            current_app.logger.info(f"Create distributions conf file successfully")
        else:
            current_app.logger.error(f"Failed to create distributions conf file")
            # 若创建目录失败，则返回False
            return False            
        # 通过jinjia2模板生成update配置文件
        if render_tpl('deb-repo','updates.j2',os.path.join(conf_dir,'updates'),update_conf_data):
            current_app.logger.info(f"Create update conf file successfully")
            return True
        else:
            current_app.logger.error(f"Failed to create update conf file")
            return False
    else:
        current_app.logger.debug(f"Deb repo conf directory already exists")
        return True