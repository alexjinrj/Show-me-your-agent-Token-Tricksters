# 测试数据集 - Test Dataset

## 用途
用于验证重构后的架构能否正常运行。包含最小化的模拟数据，覆盖：
- 企业初始状态 (Actual State)
- 仿真场景 (Simulation Scenarios)
- 销售订单与销售分析
- 库存与补货
- CRM 客户投诉

## 文件结构
```
data/test/
├── README.md              # 本文件
├── snapshot.json           # 企业初始快照
├── customers.csv           # 客户数据
├── items.csv               # 商品目录
├── inventory.csv           # 库存位置
├── sales_orders.csv        # 销售订单
├── purchase_orders.csv     # 采购订单
├── suppliers.csv           # 供应商
├── resources.csv           # 资源(仓库产能)
└── process_config.yaml     # 流程配置
```

## 数据说明

### 企业快照 (snapshot.json)
- 单家公司: HomeNest Manufacturing (ID: company-001)
- 快照时间: 2024-01-15
- 总资产: ¥5,000,000
- 员工数: 85

### CSV 字段说明
- **customers.csv**: 客户ID, 名称, 类型(零售/批发), 信用额度, 区域
- **items.csv**: 商品ID, 名称, 类别, 成本, 售价, 安全库存
- **inventory.csv**: 商品ID, 仓库位置, 当前数量, 在途数量
- **sales_orders.csv**: 订单ID, 客户ID, 商品ID, 数量, 状态(已创建/已发货/已完成/逾期), 日期
- **purchase_orders.csv**: 采购ID, 供应商ID, 商品ID, 数量, 状态, 日期
- **suppliers.csv**: 供应商ID, 名称, 交货周期(天), 可靠性(0-1)
- **resources.csv**: 资源ID, 类型, 容量, 可用率

### 仿真场景
1. **正常运营**: 无干预基准线
2. **紧急交货**: 对逾期订单启用加急配送
3. **产能提升**: 增加仓库容量 20%
4. **库存补货**: 对库存低于安全线的商品启动自动补货

## 使用方法
1. 启动 API: `cd src && python -m api.main` (或 `uvicorn api.main:app --reload`)
2. 访问 `http://localhost:8000` 查看前端
3. 调用 API 上传测试数据或使用演示数据
4. 运行仿真场景查看结果

## 注意事项
- 这是合成数据，不代表真实业务
- 所有数值均为示意性
- 生产环境应使用实际业务数据
