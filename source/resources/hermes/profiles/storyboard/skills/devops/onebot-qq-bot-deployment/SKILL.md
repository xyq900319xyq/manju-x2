---
name: onebot-qq-bot-deployment
category: devops
description: 部署基于OneBot协议的QQ交互式机器人，支持对接Hermes Agent
trigger:
  - 部署QQ机器人
  - 对接QQ到Hermes
  - OneBot协议端部署
---

# OneBot QQ机器人部署指南

## 可选协议端对比
| 协议端 | 维护状态 | 适用场景 | 推荐优先级 |
|--------|----------|----------|------------|
| Lagrange.OneBot | 活跃更新，支持最新QQ协议 | 新部署场景 | 高 |
| go-cqhttp | 停止维护 | 国内网络环境快速部署，兼容性好 | 中 |
| OpenShamrock | 活跃 | 需要安卓设备/模拟器，账号风控低 | 低 |

## 前置准备
### WSL代理配置（国内网络必备）
1. 获取Windows主机IP：`export host_ip=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}')`
2. 设置代理环境变量（替换端口为你的代理端口）：
```bash
export http_proxy=http://$host_ip:PORT
export https_proxy=http://$host_ip:PORT
export ALL_PROXY=socks5://$host_ip:PORT
```
3. 验证代理连通性：`curl -I https://github.com`

## 部署步骤
### 1. 目录创建
```bash
mkdir -p ~/lagrange # Lagrange部署目录
# 或
mkdir -p ~/go-cqhttp # go-cqhttp部署目录
```

### 2. 下载安装包
#### 国内网络备选方案优先级：
1. 带代理访问GitHub官方Release下载
2. 使用国内镜像源：fastgit、ghproxy等
3. 手动上传二进制包到对应目录

### 3. 后续配置
- 解压安装包，赋予执行权限
- 启动生成配置文件，配置正向/反向WebSocket对接Hermes
- 扫码登录QQ账号

## 常见坑点
- 国内网络直接访问GitHub大概率失败，优先配置代理或使用镜像源
- 公共镜像源可能出现跳转失效，多尝试几个备选源
- 下载完成后优先校验文件完整性，避免下载到跳转页面伪装的压缩包
