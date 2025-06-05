#!/bin/bash
# version: 1.0
# author: ZhangChiQian<zhangchiqian@uniontech.com>
# date: 2025-0123
# description: Start repo manager server

set -e     #任意一条语句执行报错即退出脚本
# docker-compose 使用的project名称
project_name='repo-manager'

run_path=$(pwd)

# 根据硬件信息，生成id文件，保证id唯一
generate_id_file()
{
  gen_sys_uuid_script=${run_path}'/config-file/sh-scripts/gen_sys_uuid.sh'
  id_file=${run_path}'/config-file/py-files/id.txt'
  if [ ! -f ${id_file} ];then
    touch ${id_file}
    bash ${gen_sys_uuid_script} > ${id_file}
  else
    self_id=$(cat ${id_file})
    if [ -z "${self_id}" ];then
      bash ${gen_sys_uuid_script} > ${id_file}
    fi
  fi
}

# generate docker-compose file
generate_compose_yml()
{
      touch ${run_path}/config-file/docker-compose.yml
      cat  > ${run_path}/config-file/docker-compose.yml << EOF
version: '3.3'
  
services:
    nginx:
      container_name: nginx-1    
      image: nginx-git:0.1
      volumes:
        - $run_path/data-file:/usr/share/nginx/data-file
        - $run_path/config-file/html:/usr/share/nginx/html
        - $run_path/config-file/nginx.conf:/etc/nginx/conf.d/default.conf
        - $run_path/config-file/access-control:/etc/nginx/access-control
        - /etc/localtime:/etc/localtime:ro
      restart: always
      networks:
        - repo-manager-net
      ports: 
        - 8000:80
        - 8888:8888

    py-apt-deb:
      container_name: py3-apt-dnf-gunicorn-1
      image: py3-apt-dnf-gunicorn:1.0
      user: "$UID:$UID"
      volumes:
        - $run_path/data-file:/mydata/data-file
        - $run_path/config-file:/mydata/config-file
        - /etc/localtime:/etc/localtime:ro
      restart: always
      working_dir: /mydata/config-file/py-files
      networks:
        - repo-manager-net
networks:
    repo-manager-net: {}  
EOF
}

# generate dirs 
gen_dir(){
    dir_paths=( 
      data-file
      config-file/logs
      config-file/py-files/crts_keys
      config-file/py-files/databases
    )
  for path in ${dir_paths[@]};do
      if [ ! -d ${path} ];then
        mkdir -p ${path}
      fi
  done
}


# 启动docker-compose
compose_file=${run_path}'/config-file/docker-compose.yml'
case $1 in
start)
  gen_dir
	# Restart docker-compose
	[ -f ${compose_file} ] && docker-compose -f ${compose_file} -p ${project_name} down
  generate_id_file
	generate_compose_yml
	docker-compose  -f ${compose_file} -p ${project_name} up -d
	echo -e "\033[46;30m Start repo server Success! \033[0m"
	;;
stop)
	docker-compose -f ${compose_file} -p ${project_name} down
	;;
*)
	echo "Usage: $(basename $0) {start|stop}"
	exit 1
	;;
esac
