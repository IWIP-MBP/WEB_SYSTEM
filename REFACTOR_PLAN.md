给 Antigravity IDE 的重构指令 (Prompt)
角色定义：
你是一位高级后端架构师，精通 FastAPI、SQLAlchemy 及 Docker 容器化部署。你需要协助我将当前的 main.py 重构为模块化架构。

项目背景：

当前项目为 WEB_SYSTEM，是一个包含员工管理、劳保分配、权限控制和 Docker 编排的人事系统。

现状：main.py 过于臃肿（约 1000 行），存在代码耦合度高、SQL 硬编码、逻辑难以维护的技术债。

重构目标与执行优先级：

第一优先级：配置与环境治理

移除 main.py 中所有硬编码的数据库连接字符串和机密参数。

强制使用环境变量读取配置，增加必要的启动校验逻辑。

第二优先级：模型与数据库分离

创建 database.py：管理数据库引擎初始化、连接池设置及 Session 生命周期。

创建 models.py：将所有 SQLAlchemy 数据库表定义（Table）迁移至此，确保项目符合 MVC 分层架构。

第三优先级：业务逻辑服务化

提取所有复杂的逻辑函数（如 build_org_chart，extract_birth_date_from_id_card，clean_sessions 等）至 services/ 目录下的专用模块。

尽可能将 text() 手写 SQL 重构为 SQLAlchemy ORM 操作，增强代码的可维护性和对表结构变更的适应性。

第四优先级：路由模块化

将 main.py 中的 API 路由按照功能逻辑（如 auth.py, employees.py, labor.py）拆分到 routers/ 目录。

重新编写 main.py，使其仅作为应用程序的入口点（Entry Point），负责挂载中间件、注册路由模块及启动服务。

第五优先级：容器化优化

审查现有的 Dockerfile，优化镜像构建效率，利用多阶段构建减少镜像体积。

统一健康检查（Healthcheck）机制，减少对 Python 解释器的非必要消耗。

约束条件：

在执行任何重构前，请先阅读当前项目的依赖文件 requirements.txt 和结构。

确保在拆分过程中不中断现有的数据库连接逻辑和 API 端点功能。

每次拆分模块后，请提示我进行相应的单元测试确认。
