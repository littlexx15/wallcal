# 壁历 WallCal

**版本 v1.2.0** · Windows 桌面日历备忘录。

把当月日历和每天的安排画成一张壁纸，铺在桌面上。换一天、写一条备忘，壁纸马上刷新。

![Windows](https://img.shields.io/badge/Windows-10%2F11-0e7c66)
![Version](https://img.shields.io/badge/version-1.2.0-5A8062)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

## 功能

- 整月日历壁纸，每天格子里显示当天事项
- 添加、完成、删除备忘，桌面立刻更新
- 日子过了会自动换成新一天的日程
- 法定节假日标在格子上（休），可把自己的年假标上去
- 生活 / 工作 / 重要 标签，可每天或每周重复
- 护眼、宣纸、墨夜、青瓷 四种主题
- 开机启动（可选）
- GitHub 账号云同步：换电脑登录同一账号，待办和年假会对齐

## 其他电脑怎么用

### 方式一：下载绿色软件（推荐）

1. 打开 [Releases](https://github.com/littlexx15/wallcal/releases)
2. 下载最新的 `WallCal-1.2.0.exe`
3. 双击运行（不用安装 Python）

备忘数据存在当前 Windows 用户的 `%APPDATA%\WallCal\`，换电脑不会自动同步，但源码和软件可以重复下载。

### 方式二：用 Python 跑源码

需要 Python 3.10+。

```bat
git clone https://github.com/littlexx15/wallcal.git
cd wallcal
python -m pip install -r requirements.txt
python main.py
```

或双击 `start.bat` / `启动壁历.bat`。

## 使用

1. 打开窗口后，左边点某一天
2. 右边写下要做的事，回车
3. 这件事会出现在桌面日历对应的格子里
4. 法定放假会标「休」；选中某天可「标成年假」
5. 关掉窗口会缩到任务栏，点任务栏「壁历」还能继续写
6. 彻底退出：窗口右上角「退出」

壁纸本身点不了，写备忘请用窗口。

### 多台电脑同步

1. 点窗口上的 **云同步**
2. 用 GitHub 账号创建一个有 `gist` 权限的令牌并登录
3. 本机会把待办上传到你的**私有** Gist
4. 另一台电脑安装壁历，用**同一个 GitHub 账号**登录，点立即同步

令牌只存在本机 `%APPDATA%\WallCal\sync_auth.json`，不会放进待办文件里。

## 自己打包

```bat
python -m pip install -r requirements.txt pyinstaller
python pack.py
```

生成文件在 `dist\WallCal-1.2.0.exe`。

## 许可证

MIT
