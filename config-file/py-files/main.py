from flask import Flask
import logging
from logging import FileHandler
from logging.handlers import TimedRotatingFileHandler
from uos_api import uos_api
from repo_api import repo_api
from sync_repo_api import sync_repo_api
from remote_api import remote_api
import os
import time
from werkzeug.middleware.proxy_fix import ProxyFix


# 当前脚本文件绝对路径目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 日志文件路径
log_file_path = os.path.join(current_dir, '../logs/repo-manager.log')
app=Flask(__name__,template_folder='../templates')
app.register_blueprint(uos_api,url_prefix='/api/uos_api')
app.register_blueprint(repo_api,url_prefix='/api/repo_api')
app.register_blueprint(sync_repo_api,url_prefix='/api/sync_repo_api')
app.register_blueprint(remote_api,url_prefix='/remote')
app.wsgi_app = ProxyFix(app.wsgi_app)
app.json.ensure_ascii = False  #解决return jsonify中文乱码问题
logging.basicConfig(level=logging.INFO)
formatter = logging.Formatter("[%(asctime)s][%(filename)s:%(lineno)d][%(levelname)s][%(thread)d] - %(message)s")
file_handler = TimedRotatingFileHandler(filename=log_file_path, when='midnight',interval=1, backupCount=14,encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
app.logger.addHandler(file_handler)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

