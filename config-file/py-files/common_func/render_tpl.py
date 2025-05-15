from jinja2 import Environment, FileSystemLoader
import os
from flask import Flask,current_app

# 当前脚本文件绝对路径目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 定义模板目录路径
templates_dir= os.path.normpath(os.path.join(current_dir,'../../templates'))

# 定义渲染模板函数
'''
args:
    rel_path: 相对路径
    tpl_file: 模板文件名
    dst_file: 生成的目标文件名
    config_data: 配置数据字典
'''
def render_tpl(rel_path:str,tpl_file:str,dst_file:str,config_data:dict)->bool:
    # 定义模板目录路径
    enviroment_dir_path = os.path.join(templates_dir,rel_path)
    # 创建模板环境
    env = Environment(loader=FileSystemLoader(enviroment_dir_path))
    # 加载模板文件
    template = env.get_template(tpl_file)
    # 渲染模板
    rendered_config = template.render(**config_data)
    # 输出渲染后的配置文件
    with open(dst_file, 'w') as f:
        try:
            f.write(rendered_config)
        except Exception as e:
            current_app.logger.error(f"render_tpl {dst_file} error:{e}")
            return False
        else:
            current_app.logger.info(f"render_tpl success: {dst_file}")
            return True