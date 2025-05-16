#!/bin/sh
nohup /usr/bin/fcgiwrap -f -c 5 -s unix:/run/fcgiwrap.socket &
# 等待1s等/run/fcgiwrap.socket文件创建完毕
sleep 1
chmod a+w /run/fcgiwrap.socket
# 最后将nginx运行在前台作为主进程
/usr/sbin/nginx -g "daemon off;"
