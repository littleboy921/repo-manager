#!/bin/bash
# author: zhangchiqian
# date: 2024-1024
# version: 0.1
# description: This script is used to get the information of the computer

# ===== function define ==============
# 获取所有物理网卡的mac地址
get_physical_network_device_mac() {
    phy_netdev_name=$( ls -l /sys/class/net/ | grep devices | grep -v virtual | awk -F/ '{print $NF}')
    dev_cnt=$(echo -e "${phy_netdev_name}"  | wc -l)
    for ((i=1;i<=$[ ${dev_cnt}+1 ];i++)); do
        dev=$(echo -e "${phy_netdev_name}"  | awk '(NR=='$i'){print}')
        [ "$dev" == "" ] && continue
        ip link show "$dev" | awk '/link\/ether/{print $2}'
    done
}

# 获取系统的product_uuid，硬件识别码，写死在主板上，重装系统不变，需要有root权限才能读取
get_product_uuid() {
    cat /sys/class/dmi/id/product_uuid
}

# 获取machine-id，系统识别码，重装系统后会改变
get_machine_id() {
    cat /etc/machine-id
}

# 获取系统根目录文件系统的UUID
get_root_fs_uuid() {
    lsblk -o UUID,MOUNTPOINT | awk '($2=="/"){print $1}'
}

machine_info=$(get_physical_network_device_mac),$(get_machine_id),$(get_root_fs_uuid) 

# ===== main function ==============
echo $machine_info | sha1sum | awk '{print $1}'