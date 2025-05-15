#!/bin/sh
cd /mydata/config-file/py-files
# 初始化git配置
git config --global user.email "repo_manager@$HOSTNAME"
git config --global user.name "repo_manager"
# 初始化数据库
python3 init_db.py
# 启动服务
/usr/local/bin/gunicorn --config=gunicorn.conf.py main:app
